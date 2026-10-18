package com.agentichumans.carddemo;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.boot.SpringApplication;

/**
 * Parity with the real COBOL: runs each migrated program on a fixture and compares every output file,
 * record by record, with the output the COBOL program produced (oracle/golden/**, captured under GnuCOBOL).
 * Fixtures are language-neutral fixed-width files, so no COBOL runtime is needed to run this test.
 */
class ParityTest {

    private static final Path ORACLE = Path.of("../../oracle");

    /** An output artifact: file, record length, and byte ranges that legitimately differ (system clock). */
    record Artifact(String file, int recordLength, int[][] maskedRanges) {}

    record Scenario(String name, String job, Path golden, List<String> args, List<Artifact> artifacts) {
        @Override public String toString() { return name; }
    }

    static final Artifact[] NO_MASK = {};
    static final int[][] PROC_TS = {{304, 330}};

    static Stream<Scenario> scenarios() {
        List<Artifact> posttran = List.of(
                new Artifact("TRANSACT.flat", 350, PROC_TS),
                new Artifact("DALYREJS.ps", 430, new int[0][]),
                new Artifact("ACCTDATA.flat", 300, new int[0][]),
                new Artifact("TCATBALF.flat", 50, new int[0][]));
        List<Artifact> intcalc = List.of(
                new Artifact("SYSTRAN.ps", 350, new int[][]{{278, 330}}),      // ORIG-TS and PROC-TS: system clock
                new Artifact("ACCTDATA.flat", 300, new int[0][]));
        Path state = ORACLE.resolve("golden/posttran/input");
        Stream<Scenario> interest = Stream.of("interest-edge", "interest-abend-account", "interest-abend-xref", "interest-abend-rate")
                .map(n -> new Scenario("intcalc/" + n, "intcalc", ORACLE.resolve("golden/" + n + "/intcalc"),
                        List.of("--carddemo.state-dir=" + ORACLE.resolve("golden/" + n),
                                "--carddemo.input-dir=" + ORACLE.resolve("golden/" + n + "/input")), intcalc));
        return Stream.concat(Stream.of(
                new Scenario("intcalc/sample", "intcalc", ORACLE.resolve("golden/posttran/intcalc"),
                        List.of("--carddemo.state-dir=" + ORACLE.resolve("golden/posttran"), "--carddemo.input-dir=" + state), intcalc),
                new Scenario("posttran/sample", "posttran", ORACLE.resolve("golden/posttran"),
                        List.of("--carddemo.input-dir=" + state,
                                "--carddemo.dailytran=" + ORACLE.resolve("golden/posttran/DALYTRAN.input")), posttran),
                new Scenario("posttran/hidden-state", "posttran", ORACLE.resolve("golden/hidden-state"),
                        List.of("--carddemo.input-dir=" + ORACLE.resolve("golden/hidden-state/input"),
                                "--carddemo.dailytran=" + ORACLE.resolve("scenarios/hidden-state/DALYTRAN.input")), posttran),
                new Scenario("posttran/edge-cases", "posttran", ORACLE.resolve("golden/edge"),
                        List.of("--carddemo.input-dir=" + state,
                                "--carddemo.dailytran=" + ORACLE.resolve("scenarios/edge/DALYTRAN.input")), posttran)),
                interest);
    }

    @ParameterizedTest(name = "{0}")
    @MethodSource("scenarios")
    void matchesCobolOutput(Scenario s, @TempDir Path out) throws IOException {
        List<String> args = new java.util.ArrayList<>(s.args());
        args.add("--carddemo.job=" + s.job());
        args.add("--carddemo.output-dir=" + out);
        try (var ctx = SpringApplication.run(CardDemoApplication.class, args.toArray(String[]::new))) {
            assertTrue(ctx.isRunning());
        }
        assertEquals(Files.readString(s.golden().resolve("rc.txt")).trim(),
                Files.readString(out.resolve("rc.txt")).trim(), "return code");
        assertEquals(counters(s.golden().resolve("stdout.txt")), counters(out.resolve("stdout.txt")), "counters");
        for (Artifact a : s.artifacts()) {
            byte[] want = Files.readAllBytes(s.golden().resolve(a.file()));
            byte[] got = Files.readAllBytes(out.resolve(a.file()));
            assertEquals(want.length / a.recordLength(), got.length / a.recordLength(), a.file() + ": record count");
            for (int off = 0; off < want.length; off += a.recordLength()) {
                int rec = off / a.recordLength();
                byte[] w = java.util.Arrays.copyOfRange(want, off, off + a.recordLength());
                byte[] g = java.util.Arrays.copyOfRange(got, off, off + a.recordLength());
                for (int[] m : a.maskedRanges()) { java.util.Arrays.fill(w, m[0], m[1], (byte) '#'); java.util.Arrays.fill(g, m[0], m[1], (byte) '#'); }
                assertArrayEquals(w, g, a.file() + ": record " + rec + " differs");
            }
        }
    }

    private static List<String> counters(Path p) throws IOException {
        return Files.readAllLines(p).stream().filter(l -> l.contains("PROCESSED") || l.contains("REJECTED")).toList();
    }
}
