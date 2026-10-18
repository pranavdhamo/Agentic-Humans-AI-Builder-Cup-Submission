# What you can test on the VM

The VM runs the **batch** programs only. There are no screens, so you test by running a program and reading its output, or the data before and after.
Everything below was run on the VM and worked, unless marked otherwise. Run the commands in the VM terminal (see `RESTART-VM.md` to start it).

## Setup (once per terminal session)
```bash
cd /opt/carddemo-env
export COB_LIBRARY_PATH=bin
export DD_ACCTFILE=data/ACCTDATA.vsam DD_TCATBALF=data/TCATBALF.vsam
```

## Test 1: Look up an account balance
```bash
sudo -E bin/ACCTDUMP                    # all 50 accounts, one line each
sudo -E bin/ACCTDUMP 00000000001        # just one account
```
Example line: `00000000001 Y BAL  0000000194.00 LIMIT  0000002020.00` (status, balance, credit limit).

`ACCTDUMP` is our own helper (`stubs/ACCTDUMP.cbl`). The original `CBACT01C` prints only the first account, then stops with `module 'COBDATFT' not found`, because that module is a mainframe assembler routine. Don't use `CBACT01C` to browse accounts.

## Test 2: The "end of day" before and after (the main test)
```bash
sudo ./load-data.sh                    # 1. RESET data to the original sample
sudo -E bin/ACCTDUMP 00000000001       # 2. BEFORE
sudo ./run-batch.sh                    # 3. post transactions, calculate interest, build the report
sudo -E bin/ACCTDUMP 00000000001       # 4. AFTER
```
Verified for account 1: **194.00 before, 1,302.66 after**.
`run-batch.sh` prints `PROCESSED 300`, `REJECTED 38`, `rc=4` for POSTTRAN (normal, it had rejects), then `rc=0` for INTCALC and for the report.

**Always reset first.** Every `run-batch.sh` posts the same daily transactions again, so balances keep growing.

## Test 3: Why transactions were rejected
```bash
sudo head -c 600 out/DALYREJS.ps
```
Each of the 38 rejected records ends with a reason, for example `OVERLIMIT TRANSACTION`. I read one reason, not all 38.
The file is fixed-width with no line breaks, so use `head -c` and `wc -c`, not `wc -l`.

## Test 4: The daily transaction report (CBTRN03C)
`run-batch.sh` now builds this report as its last step.
```bash
sudo fold -w133 out/TRANREPT.txt | less
```
Verified: 262 posted transactions grouped by account, with account totals, page totals and a **Grand Total of 78,720.36**.
The real job first copies the transaction file to a flat file and sorts it by card number. The script does that with `stubs/TRANFLAT.cbl` plus a short sort. To change the date range: `REPORT_RANGE="2022-06-01 2022-06-30" sudo -E ./run-batch.sh`.
A quirk in the output: the first account's "Account Total" line prints twice. I didn't investigate it.

## Test 5: Verify the interest calculation by hand
Interest is, per account, the sum over its category balances of `balance x annual rate / 1200`, cut off (not rounded) at 2 decimals.
Verified on the VM: after posting, I recomputed this independently from the category balances and the rate table, and compared with how much INTCALC changed each balance.

**Result: 49 of 50 accounts match to the cent. Account 50 gets no interest applied.** I expected 18.77 and the balance did not change.

Cause (from reading `CBACT04C.cbl`, not proven by a fix): the program applies an account's interest when it reaches the *next* account. The code meant to handle the final account sits in a branch the loop can never reach. So the last account in the file never gets its interest. This is in the program's source, so a real mainframe would most likely behave the same. It is a good bug for a migration to find, or to deliberately preserve.

All accounts use the `DEFAULT` rate row, because the sample accounts' group field is blank. That is why the log prints "DISCLOSURE GROUP RECORD MISSING / TRY WITH DEFAULT GROUP CODE" for each one. It is the program's normal fallback, not an error.

## Test 6: Browse the other data
```bash
export DD_CARDFILE=data/CARDDATA.vsam DD_XREFFILE=data/CARDXREF.vsam DD_CUSTFILE=data/CUSTDATA.vsam
export DD_OUTFILE=/tmp/o1 DD_ARRYFILE=/tmp/o2 DD_VBRCFILE=/tmp/o3
sudo -E bin/CBACT02C | head      # credit cards
sudo -E bin/CBACT03C | head      # card-to-account links (xref)
sudo -E bin/CBCUS01C | head      # customers (name, address, phone)
```
These programs print each record twice. That is the program's own behaviour.

## Test 7: The transaction check (CBTRN01C)
Reads each daily transaction and looks up its card, account and customer. It ended with `rc=0` and 1,807 lines of "SUCCESSFUL READ" output. I did not check its output line by line.

## Reading raw amounts
Amounts use an old style where the last character carries the sign: `{` means digit 0 and positive, `A` to `I` mean 1 to 9 and positive. The last two digits are cents.
`00000001940{` is 194.00. `00000020200{` is 2,020.00. The programs and helpers print decoded values, so you rarely need this.

## What you cannot test
- Login, menus and screens (CICS, the "Account View" screen).
- The Db2, IMS and MQ features (authorizations, fraud flagging, transaction types).
- `CBSTM03A/B` statements, `CBEXPORT` and `CBIMPORT`.

## Stop the VM when done
```bash
gcloud compute instances stop carddemo-legacy --zone us-central1-a
```
