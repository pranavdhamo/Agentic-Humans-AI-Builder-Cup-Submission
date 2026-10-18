package com.agentichumans.carddemo.cobol;

import java.io.BufferedInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStreamException;
import org.springframework.batch.item.ItemStreamReader;

/** Mainframe sequential files are fixed-length with NO line breaks, so read {@code length}-byte records. */
public final class FixedRecordReader implements ItemStreamReader<String> {
    private final Path file;
    private final int length;
    private InputStream in;

    public FixedRecordReader(Path file, int length) { this.file = file; this.length = length; }

    @Override public void open(ExecutionContext ctx) {
        try { in = new BufferedInputStream(Files.newInputStream(file)); }
        catch (IOException e) { throw new ItemStreamException("ERROR OPENING " + file, e); }
    }

    @Override public String read() throws IOException {
        byte[] rec = in.readNBytes(length);
        if (rec.length == 0) return null;                            // file status '10' -> END-OF-FILE
        if (rec.length < length) throw new IOException("Short record in " + file + " (" + rec.length + " bytes)");
        return new String(rec, StandardCharsets.ISO_8859_1);
    }

    @Override public void close() {
        try { if (in != null) in.close(); } catch (IOException ignored) {}
    }

    /** Read a whole fixed-width file into records (used to load VSAM-like state). */
    public static java.util.List<String> readAll(Path file, int length) throws IOException {
        byte[] all = Files.readAllBytes(file);
        java.util.List<String> out = new java.util.ArrayList<>();
        for (int i = 0; i + length <= all.length; i += length)
            out.add(new String(all, i, length, StandardCharsets.ISO_8859_1));
        return out;
    }
}
