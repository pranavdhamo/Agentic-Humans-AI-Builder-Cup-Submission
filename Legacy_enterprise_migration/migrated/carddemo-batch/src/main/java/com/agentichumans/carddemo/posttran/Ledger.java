package com.agentichumans.carddemo.posttran;

import com.agentichumans.carddemo.cobol.Records;
import com.agentichumans.carddemo.cobol.CobolNumeric;
import com.agentichumans.carddemo.cobol.Records.Account;
import com.agentichumans.carddemo.cobol.Records.TranCatBal;
import com.agentichumans.carddemo.cobol.Records.Xref;
import java.io.IOException;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import java.util.TreeMap;

/**
 * In-memory stand-in for the three VSAM files CBTRN02C uses (XREF, ACCOUNT, TCATBAL). Keyed, kept in key order.
 * Replace with Cloud SQL / AlloyDB repositories in production; the posting rules do not change.
 */
final class Ledger {
    final Map<String, Xref> xref = new HashMap<>();
    final TreeMap<String, Account> accounts = new TreeMap<>();
    final TreeMap<String, TranCatBal> tcat = new TreeMap<>();

    /**
     * COBOL WORKING-STORAGE buffer behind "READ TCATBAL-FILE INTO TRAN-CAT-BAL-RECORD". It is only overwritten
     * by a SUCCESSFUL read, and INITIALIZE does not touch FILLER, so a newly created record inherits the
     * FILLER of the last record read (zeros in the sample data; spaces before any read succeeds).
     */
    TranCatBal tcatWs = new TranCatBal("00000000000" + "  " + "0000" + "00000000000" + " ".repeat(22));

    static Ledger load(Path inputDir) throws IOException {
        Ledger l = new Ledger();
        for (String r : lines(inputDir.resolve("cardxref.txt"), Records.XREF_LEN))
            l.xref.putIfAbsent(r.substring(0, 16), new Xref(r));
        for (String r : lines(inputDir.resolve("acctdata.txt"), Records.ACCOUNT_LEN))
            l.accounts.putIfAbsent(r.substring(0, 11), new Account(r));
        for (String r : lines(inputDir.resolve("tcatbal.txt"), Records.TCATBAL_LEN))
            l.tcat.putIfAbsent(r.substring(0, 17), new TranCatBal(r));
        return l;
    }

    /** LINE SEQUENTIAL load: short lines are padded with spaces to the record length. */
    private static Iterable<String> lines(Path p, int len) throws IOException {
        return Files.readAllLines(p, StandardCharsets.ISO_8859_1).stream()
                .map(s -> s.replace("\r", ""))
                .filter(s -> !s.isEmpty())
                .map(s -> CobolNumeric.padRight(s, len))
                .toList();
    }

    /** 2700-UPDATE-TCATBAL (+ 2700-A create / 2700-B update). */
    void updateCategoryBalance(String acctId, String typeCd, String catCd, BigDecimal amt) {
        String key = acctId + typeCd + catCd;
        TranCatBal found = tcat.get(key);
        boolean create = found == null;
        if (!create) tcatWs = new TranCatBal(found.raw());          // READ ... INTO: only on success
        if (create) {                                               // 2700-A: INITIALIZE (FILLER untouched)
            tcatWs.setKey(key);
            tcatWs.bal(BigDecimal.ZERO);
        }
        tcatWs.bal(tcatWs.bal().add(amt));                          // ADD DALYTRAN-AMT TO TRAN-CAT-BAL
        tcat.put(key, new TranCatBal(tcatWs.raw()));                // WRITE (create) / REWRITE (update)
    }

    /** 2800-UPDATE-ACCOUNT-REC. {@code acct} is the working copy read during validation. */
    void updateAccount(Account acct, BigDecimal amt) {
        acct.currBal(acct.currBal().add(amt));
        if (amt.signum() >= 0) acct.cycCredit(acct.cycCredit().add(amt));
        else acct.cycDebit(acct.cycDebit().add(amt));
        accounts.put(acct.key(), new Account(acct.raw()));          // REWRITE
    }
}
