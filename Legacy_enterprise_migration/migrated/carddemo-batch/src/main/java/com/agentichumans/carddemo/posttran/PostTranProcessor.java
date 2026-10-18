package com.agentichumans.carddemo.posttran;

import com.agentichumans.carddemo.cobol.Records;
import com.agentichumans.carddemo.cobol.CobolNumeric;
import com.agentichumans.carddemo.cobol.Records.Account;
import com.agentichumans.carddemo.cobol.Records.Tran;
import com.agentichumans.carddemo.cobol.Records.Xref;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.function.Supplier;
import org.springframework.batch.item.ItemProcessor;

/**
 * Port of CBTRN02C paragraphs 1500-VALIDATE-TRAN and 2000-POST-TRANSACTION.
 *
 * <p>Validation AND posting both happen here, not in the writer: COBOL processes one transaction at a time and
 * validation of record N must see the balances posted by record N-1. Doing the update in an ItemWriter would
 * make the whole chunk validate against stale balances.
 */
final class PostTranProcessor implements ItemProcessor<String, PostTranProcessor.Outcome> {

    sealed interface Outcome permits Posted, Rejected {}
    record Posted(String id, String tranRecord) implements Outcome {}
    record Rejected(String rejectRecord) implements Outcome {}

    private final Ledger ledger;
    private final RunState state;
    private final Supplier<LocalDateTime> clock;

    PostTranProcessor(Ledger ledger, RunState state, Supplier<LocalDateTime> clock) {
        this.ledger = ledger; this.state = state; this.clock = clock;
    }

    @Override
    public Outcome process(String raw) {
        state.processed++;                                           // ADD 1 TO WS-TRANSACTION-COUNT
        Tran tran = new Tran(raw);
        int reason = 0;
        String desc = "";

        // 1500-A-LOOKUP-XREF
        Xref xref = ledger.xref.get(tran.cardNum());
        Account acct = null;
        if (xref == null) {
            reason = 100; desc = "INVALID CARD NUMBER FOUND";
        } else {
            // 1500-B-LOOKUP-ACCT
            Account found = ledger.accounts.get(xref.acctId());
            if (found == null) {
                reason = 101; desc = "ACCOUNT RECORD NOT FOUND";
            } else {
                acct = new Account(found.raw());
                BigDecimal tempBal = CobolNumeric.fit(
                        acct.cycCredit().subtract(acct.cycDebit()).add(tran.amt()), 9, 2);   // WS-TEMP-BAL S9(09)V99
                if (acct.creditLimit().compareTo(tempBal) < 0) {
                    reason = 102; desc = "OVERLIMIT TRANSACTION";
                }
                // Not an ELSE: this check always runs and, if it fails, OVERWRITES the over-limit reason.
                if (acct.expiryDate().compareTo(tran.origDate()) < 0) {
                    reason = 103; desc = "TRANSACTION RECEIVED AFTER ACCT EXPIRATION";
                }
            }
        }

        if (reason != 0) {                                           // 2500-WRITE-REJECT-REC
            state.rejected++;
            String trailer = String.format("%04d", reason) + CobolNumeric.padRight(desc, 76);
            return new Rejected(raw + trailer);
        }

        // 2000-POST-TRANSACTION
        String procTs = CobolNumeric.db2Timestamp(clock.get());
        ledger.updateCategoryBalance(xref.acctId(), tran.typeCd(), tran.catCd(), tran.amt());
        ledger.updateAccount(acct, tran.amt());
        return new Posted(tran.id(), tran.posted(procTs));
    }
}
