package com.agentichumans.carddemo.cobol;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

/**
 * COBOL DISPLAY-numeric semantics that Java does not give you for free.
 *
 * <p>Signed fields (PIC S9(n)V99) store the sign inside the LAST character ("overpunch", EBCDIC style):
 * {@code '{'}=+0, {@code A-I}=+1..+9, {@code '}'}=-0, {@code J-R}=-1..-9.
 * Arithmetic without ROUNDED TRUNCATES extra decimals toward zero and drops overflowing high-order digits.
 */
public final class CobolNumeric {
    private CobolNumeric() {}

    private static final String POS = "{ABCDEFGHI";
    private static final String NEG = "}JKLMNOPQR";

    /** Decode a signed overpunch DISPLAY field with {@code scale} implied decimals. */
    public static BigDecimal decodeSigned(String field, int scale) {
        char last = field.charAt(field.length() - 1);
        int digit;
        boolean negative = false;
        int p = POS.indexOf(last), n = NEG.indexOf(last);
        if (p >= 0) digit = p;
        else if (n >= 0) { digit = n; negative = true; }
        else if (last >= '0' && last <= '9') digit = last - '0';
        else throw new IllegalArgumentException("Not a numeric field: '" + field + "'");
        String digits = field.substring(0, field.length() - 1) + digit;
        BigDecimal v = new BigDecimal(new BigInteger(digits), scale);
        return negative ? v.negate() : v;
    }

    /** Decode an unsigned PIC 9(n) field. */
    public static long decodeUnsigned(String field) {
        return Long.parseLong(field.trim());
    }

    /** Apply COBOL storage rules for PIC S9(intDigits)V9(scale): truncate decimals, drop high-order overflow. */
    public static BigDecimal fit(BigDecimal v, int intDigits, int scale) {
        BigInteger unscaled = v.setScale(scale, RoundingMode.DOWN).unscaledValue();
        BigInteger mod = BigInteger.TEN.pow(intDigits + scale);
        BigInteger kept = unscaled.abs().mod(mod);
        return new BigDecimal(unscaled.signum() < 0 ? kept.negate() : kept, scale);
    }

    /** Encode into a signed overpunch DISPLAY field of intDigits+scale characters. */
    public static String encodeSigned(BigDecimal v, int intDigits, int scale) {
        BigDecimal f = fit(v, intDigits, scale);
        String digits = String.format("%0" + (intDigits + scale) + "d", f.unscaledValue().abs());
        int last = digits.charAt(digits.length() - 1) - '0';
        char sign = f.signum() < 0 ? NEG.charAt(last) : POS.charAt(last);
        return digits.substring(0, digits.length() - 1) + sign;
    }

    public static String padRight(String s, int len) {
        if (s.length() >= len) return s.substring(0, len);
        return s + " ".repeat(len - s.length());
    }

    /** Z-GET-DB2-FORMAT-TIMESTAMP: YYYY-MM-DD-HH.MM.SS.hh0000 (hundredths of a second + '0000'). */
    public static String db2Timestamp(java.time.LocalDateTime t) {
        return String.format("%04d-%02d-%02d-%02d.%02d.%02d.%02d0000",
                t.getYear(), t.getMonthValue(), t.getDayOfMonth(), t.getHour(), t.getMinute(), t.getSecond(),
                t.getNano() / 10_000_000);
    }
}
