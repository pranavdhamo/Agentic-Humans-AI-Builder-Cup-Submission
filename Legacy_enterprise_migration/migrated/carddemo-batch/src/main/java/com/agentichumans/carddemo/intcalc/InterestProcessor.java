package com.agentichumans.carddemo.intcalc;

import com.agentichumans.carddemo.cobol.CobolNumeric;
import com.agentichumans.carddemo.cobol.Records.Account;
import com.agentichumans.carddemo.cobol.Records.DisGroup;
import com.agentichumans.carddemo.cobol.Records.TranCatBal;
import com.agentichumans.carddemo.cobol.Records.Xref;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.util.function.Supplier;
import org.springframework.batch.item.ItemProcessor;

/**
 * Port of CBACT04C's main loop. Input: transaction-category balances in key order (so grouped by account).
 * Output: one interest transaction per category with a non-zero rate; accounts are updated as a side effect.
 *
 * <p>LEGACY BEHAVIOUR PRESERVED: an account's interest is applied when the NEXT account is reached
 * (1050-UPDATE-ACCOUNT). The COBOL branch meant to flush the last account is unreachable (it sits in the ELSE of a
 * loop that has already exited), so the last account's interest transactions are written but its balance is never
 * updated. Set {@code fixLastAccount} to apply the evident intent instead.
 */
final class InterestProcessor implements ItemProcessor<String, String> {

    private final InterestLedger ledger;
    private final InterestState state;
    private final String parmDate;
    private final boolean fixLastAccount;
    private final Supplier<LocalDateTime> clock;

    private String lastAcctNum = " ".repeat(11);      // WS-LAST-ACCT-NUM
    private boolean firstTime = true;                 // WS-FIRST-TIME
    private BigDecimal totalInt = BigDecimal.ZERO;    // WS-TOTAL-INT  S9(09)V99
    private int tranIdSuffix;                         // WS-TRANID-SUFFIX 9(06)

    InterestProcessor(InterestLedger ledger, InterestState state, String parmDate, boolean fixLastAccount,
                      Supplier<LocalDateTime> clock) {
        this.ledger = ledger; this.state = state; this.parmDate = parmDate;
        this.fixLastAccount = fixLastAccount; this.clock = clock;
    }

    @Override
    public String process(String raw) {
        if (state.abend != null) return null;                    // the COBOL run already ended
        state.recordCount++;
        TranCatBal cat = new TranCatBal(raw);
        String acctId = raw.substring(0, 11), typeCd = raw.substring(11, 13), catCd = raw.substring(13, 17);

        if (!acctId.equals(lastAcctNum)) {
            if (!firstTime) updateAccount();          // 1050: settle the PREVIOUS account
            else firstTime = false;
            totalInt = BigDecimal.ZERO;
            lastAcctNum = acctId;
            Account acct = ledger.accounts.get(acctId);          // 1100-GET-ACCT-DATA
            if (acct == null) return abend("ACCOUNT NOT FOUND: " + acctId);
            ledger.accountWs = new Account(acct.raw());
            Xref xref = ledger.xrefByAcct.get(acctId);           // 1110-GET-XREF-DATA
            if (xref == null) return abend("ACCOUNT NOT FOUND IN XREF: " + acctId);
            ledger.xrefWs = xref;
        }

        if (!lookupInterestRate(ledger.accountWs.groupId(), typeCd, catCd)) return null;   // 1200-GET-INTEREST-RATE
        BigDecimal rate = ledger.disWs.rate();
        if (rate.signum() == 0) return null;

        // 1300-COMPUTE-INTEREST: (balance * rate) / 1200, stored WITHOUT ROUNDED, i.e. truncated to 2 decimals
        BigDecimal monthly = CobolNumeric.fit(
                cat.bal().multiply(rate).divide(BigDecimal.valueOf(1200), 2, RoundingMode.DOWN), 9, 2);
        totalInt = CobolNumeric.fit(totalInt.add(monthly), 9, 2);
        return interestTransaction(monthly);                     // 1300-B-WRITE-TX
    }

    /** Called by the job when the input is exhausted. The legacy program never settles the last account. */
    void endOfFile() {
        if (fixLastAccount && !firstTime && state.abend == null) updateAccount();
    }

    /** 1050-UPDATE-ACCOUNT: post accumulated interest, reset the cycle credit/debit, REWRITE the buffered record. */
    private void updateAccount() {
        Account a = ledger.accountWs;
        a.currBal(a.currBal().add(totalInt));
        a.cycCredit(BigDecimal.ZERO);
        a.cycDebit(BigDecimal.ZERO);
        ledger.accounts.put(a.key(), new Account(a.raw()));
    }

    /** 1200 + 1200-A: exact group first; if absent fall back to the DEFAULT group; if that is absent too, abend. */
    private boolean lookupInterestRate(String groupId, String typeCd, String catCd) {
        DisGroup d = ledger.discGroups.get(groupId + typeCd + catCd);
        if (d == null) d = ledger.discGroups.get(CobolNumeric.padRight("DEFAULT", 10) + typeCd + catCd);
        if (d == null) { abend("ERROR READING DEFAULT DISCLOSURE GROUP: " + typeCd + catCd); return false; }
        ledger.disWs = d;
        return true;
    }

    /** 9999-ABEND-PROGRAM: stop; keep what was already written. */
    private String abend(String why) {
        state.abend = why;
        return null;
    }

    private String interestTransaction(BigDecimal monthly) {
        tranIdSuffix = (tranIdSuffix + 1) % 1_000_000;
        String ts = CobolNumeric.db2Timestamp(clock.get());
        return parmDate + String.format("%06d", tranIdSuffix)                 // TRAN-ID
                + "01" + "0005" + CobolNumeric.padRight("System", 10)         // type, category, source
                + CobolNumeric.padRight("Int. for a/c " + ledger.accountWs.key(), 100)
                + CobolNumeric.encodeSigned(monthly, 9, 2)                    // TRAN-AMT
                + "000000000" + " ".repeat(50) + " ".repeat(50) + " ".repeat(10)  // merchant id, name, city, zip
                + ledger.xrefWs.cardNum() + ts + ts + " ".repeat(20);         // card, orig-ts, proc-ts, filler
    }
}
