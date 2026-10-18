package com.agentichumans.carddemo.cobol;

import java.math.BigDecimal;

/** Fixed-width record layouts (from CardDemo copybooks CVTRA06Y, CVACT01Y, CVACT03Y, CVTRA01Y, CVTRA05Y). */
public final class Records {
    private Records() {}

    public static final int DALYTRAN_LEN = 350, ACCOUNT_LEN = 300, XREF_LEN = 50, TCATBAL_LEN = 50, REJECT_LEN = 430;

    /** DALYTRAN-RECORD / TRAN-RECORD share one layout, except PROC-TS which TRAN-RECORD fills in. */
    public record Tran(String raw) {
        public String id()         { return raw.substring(0, 16); }
        public String typeCd()     { return raw.substring(16, 18); }
        public String catCd()      { return raw.substring(18, 22); }
        public BigDecimal amt()    { return CobolNumeric.decodeSigned(raw.substring(132, 143), 2); }
        public String cardNum()    { return raw.substring(262, 278); }
        public String origDate()   { return raw.substring(278, 288); }   // DALYTRAN-ORIG-TS (1:10)

        /** Build the TRAN-RECORD posted to the transaction master: same fields, new PROC-TS, FILLER spaces. */
        public String posted(String procTs) {
            return raw.substring(0, 304) + procTs + " ".repeat(20);
        }
    }

    /** ACCOUNT-RECORD, 300 bytes. Only the fields CBTRN02C touches are exposed. */
    public static final class Account {
        private StringBuilder b;
        public Account(String raw) { b = new StringBuilder(raw); }
        public String raw()                { return b.toString(); }
        public String key()                { return b.substring(0, 11); }
        public String expiryDate()         { return b.substring(58, 68); }
        public String groupId()            { return b.substring(112, 122); }
        public BigDecimal currBal()        { return num(12, 24); }
        public BigDecimal creditLimit()    { return num(24, 36); }
        public BigDecimal cycCredit()      { return num(78, 90); }
        public BigDecimal cycDebit()       { return num(90, 102); }
        public void currBal(BigDecimal v)  { set(12, 24, v); }
        public void cycCredit(BigDecimal v){ set(78, 90, v); }
        public void cycDebit(BigDecimal v) { set(90, 102, v); }
        private BigDecimal num(int from, int to) { return CobolNumeric.decodeSigned(b.substring(from, to), 2); }
        private void set(int from, int to, BigDecimal v) {
            b.replace(from, to, CobolNumeric.encodeSigned(v, 10, 2));
        }
    }

    /** CARD-XREF-RECORD: card number -> account id. */
    public record Xref(String raw) {
        public String acctId() { return raw.substring(25, 36); }
        public String cardNum() { return raw.substring(0, 16); }
    }

    /** TRAN-CAT-BAL-RECORD, 50 bytes: acct(11) type(2) cat(4) balance S9(9)V99 filler(22). */
    public static final class TranCatBal {
        private StringBuilder b;
        public TranCatBal(String raw) { b = new StringBuilder(raw); }
        public String raw()           { return b.toString(); }
        public String key()           { return b.substring(0, 17); }
        public BigDecimal bal()       { return CobolNumeric.decodeSigned(b.substring(17, 28), 2); }
        public void bal(BigDecimal v) { b.replace(17, 28, CobolNumeric.encodeSigned(v, 9, 2)); }
        public String filler()        { return b.substring(28); }
        public void setKey(String key) { b.replace(0, 17, key); }
    }

    /** DIS-GROUP-RECORD (CVTRA02Y), 50 bytes: group(10) type(2) category(4) annual interest rate S9(4)V99 filler(28). */
    public static final class DisGroup {
        private final String raw;
        public DisGroup(String raw) { this.raw = raw; }
        public String key()      { return raw.substring(0, 16); }
        public BigDecimal rate() { return CobolNumeric.decodeSigned(raw.substring(16, 22), 2); }
    }
}
