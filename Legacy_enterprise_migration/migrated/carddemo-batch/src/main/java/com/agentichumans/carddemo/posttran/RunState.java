package com.agentichumans.carddemo.posttran;

import java.util.ArrayList;
import java.util.List;

/** Counters and output buffers for one run (the COBOL WS-COUNTERS plus the files it writes). */
final class RunState implements com.agentichumans.carddemo.cobol.RunResult {
    int processed;
    int rejected;
    final List<String> rejects = new ArrayList<>();                                   // DALYREJS, arrival order
    final List<PostTranProcessor.Posted> posted = new ArrayList<>();                  // TRANSACT, written in key order
    @Override public int returnCode() { return rejected > 0 ? 4 : 0; }              // MOVE 4 TO RETURN-CODE
    @Override public String summary() { return "processed=" + processed + " rejected=" + rejected; }
}
