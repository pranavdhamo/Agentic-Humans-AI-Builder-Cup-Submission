# Project summary

## What it is
A proof that legacy COBOL can be migrated to modern Java **and that the migration is correct**. The project takes two
batch programs from AWS's CardDemo credit-card system, ports them to Java (Spring Batch), and has Google Gemini do the
same port automatically. Correctness is judged by comparing every output record against what the **original COBOL
actually produced**, not against a model's opinion.

## The problem
Banks run critical batch jobs in COBOL. Rewriting them is risky because the old code has quirks nobody documented, and a
rewrite that "looks right" can silently change money. Teams need evidence, not trust.

## The approach
1. **Oracle:** run the real COBOL under GnuCOBOL on many scenarios and store the output as golden files.
2. **Migrate:** Gemini reads the COBOL and copybooks and writes a Java Spring Batch project.
3. **Verify:** build the Java, run it on the same inputs, and diff every field of every record against the golden files.
4. **Repair:** feed field-level mismatches back to Gemini and retry until identical or out of attempts.

## What is covered
| Program | COBOL | Does | Scenarios |
|---|---|---|---|
| Daily transaction posting | `CBTRN02C` | validates and posts transactions, rejects bad ones, updates balances | sample, edge (122 txns), hidden-state |
| Monthly interest | `CBACT04C` | computes interest per account/category and writes interest transactions | sample, interest-edge, 3 abend cases |

All 8 scenarios pass for the hand-written reference ports (verified: `python verifier/check_all.py`).

## Key findings
- Gemini (`gemini-3.8-flash`) got the business rules right first time; its one miss was COBOL's hidden working-storage
  state, fixed in one repair.
- A first "pass" was a **false pass** (hard-coded zero filler). A harder scenario exposed it, which is why scenario design matters.
- Interest migration passed first time, including the legacy bug where the last account's balance is never settled.
  Java preserves that bug by default and has a switch to apply the evident intent.
- Cost per migration: roughly 13K-29K tokens in, 5K-9K out, 3-7 minutes. Single runs per setting, so indicative only.
- A mutation check breaks the Java port 27 ways; the verifier catches all of them.

## Legacy quirks reproduced exactly
Sign stored in the last digit, truncating arithmetic with overflow wrap, "expired" overriding "over limit" rejections,
new records inheriting filler from the last record read, and abends (rc 16) that keep partial work.

## Status and what's left
Working: oracle, reference ports, verifier, Gemini loop, an offline mock mode, GCP legacy VM scripts.
Not done: UI/dashboard, CI, Vertex AI auth, remaining batch programs, data migration (VSAM to a database), and the
CICS online screens (not runnable under GnuCOBOL). See [HANDOVER.md](HANDOVER.md).

## Where to go next
[README.md](README.md) · [BOOTUP.md](BOOTUP.md) (run it) · [architecture.md](architecture.md) · [MIGRATION_PIPELINE.md](MIGRATION_PIPELINE.md)
