package com.agentichumans.carddemo.intcalc;

import com.agentichumans.carddemo.cobol.CobolNumeric;
import com.agentichumans.carddemo.cobol.FixedRecordReader;
import com.agentichumans.carddemo.cobol.Records;
import com.agentichumans.carddemo.cobol.Records.Account;
import com.agentichumans.carddemo.cobol.Records.DisGroup;
import com.agentichumans.carddemo.cobol.Records.Xref;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import java.util.TreeMap;

/**
 * Stand-in for the files CBACT04C uses: ACCOUNT, XREF (by account id = the alternate key) and DISCGRP.
 * Also holds the program's WORKING-STORAGE record buffers (the current account / card cross-reference / rate row).
 * A failed keyed READ is not tolerated by the program: it abends (see InterestProcessor).
 */
final class InterestLedger {
    final TreeMap<String, Account> accounts = new TreeMap<>();
    final Map<String, Xref> xrefByAcct = new HashMap<>();
    final Map<String, DisGroup> discGroups = new HashMap<>();

    Account accountWs = new Account("0".repeat(11) + " " + "0".repeat(48) + " ".repeat(30) + "0".repeat(24) + " ".repeat(20) + " ".repeat(178));
    Xref xrefWs = new Xref(" ".repeat(16) + "0".repeat(9) + "0".repeat(11) + " ".repeat(14));
    DisGroup disWs = new DisGroup(" ".repeat(10) + "  " + "0000" + "00000{" + " ".repeat(28));

    /** @param stateDir ACCTDATA.flat (state after POSTTRAN) @param inputDir cardxref.txt and discgrp.txt (line files) */
    static InterestLedger load(Path stateDir, Path inputDir) throws IOException {
        InterestLedger l = new InterestLedger();
        for (String r : FixedRecordReader.readAll(stateDir.resolve("ACCTDATA.flat"), Records.ACCOUNT_LEN))
            l.accounts.putIfAbsent(r.substring(0, 11), new Account(r));
        for (String r : lines(inputDir.resolve("cardxref.txt"), Records.XREF_LEN)) {
            Xref x = new Xref(r);
            l.xrefByAcct.putIfAbsent(x.acctId(), x);          // alternate key: first record wins
        }
        for (String r : lines(inputDir.resolve("discgrp.txt"), 50)) {
            DisGroup d = new DisGroup(r);
            l.discGroups.putIfAbsent(d.key(), d);
        }
        return l;
    }

    private static Iterable<String> lines(Path p, int len) throws IOException {
        return Files.readAllLines(p, StandardCharsets.ISO_8859_1).stream()
                .map(s -> s.replace("\r", "")).filter(s -> !s.isEmpty())
                .map(s -> CobolNumeric.padRight(s, len)).toList();
    }
}
