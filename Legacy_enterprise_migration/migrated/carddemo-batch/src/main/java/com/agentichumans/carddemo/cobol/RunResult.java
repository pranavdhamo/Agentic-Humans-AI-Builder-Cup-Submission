package com.agentichumans.carddemo.cobol;

/** What a finished batch program reports back, COBOL-style: a return code plus counters for the console. */
public interface RunResult {
    int returnCode();
    String summary();
}
