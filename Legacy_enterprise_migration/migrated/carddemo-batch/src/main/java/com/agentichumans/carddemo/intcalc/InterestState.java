package com.agentichumans.carddemo.intcalc;

import com.agentichumans.carddemo.cobol.RunResult;
import java.util.ArrayList;
import java.util.List;

/** Counters and the interest-transaction file (SYSTRAN) for one INTCALC run. */
final class InterestState implements RunResult {
    int recordCount;
    final List<String> interestTransactions = new ArrayList<>();
    /** 9999-ABEND-PROGRAM: processing stops, work already done is kept, return code 16 (the CEE3ABD stand-in's). */
    String abend;
    @Override public int returnCode() { return abend != null ? 16 : 0; }
    @Override public String summary() { return "tcatbal records=" + recordCount + " interest transactions=" + interestTransactions.size() + (abend != null ? " ABEND: " + abend : ""); }
}
