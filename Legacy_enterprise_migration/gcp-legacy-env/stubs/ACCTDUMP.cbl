       IDENTIFICATION DIVISION.
       PROGRAM-ID. ACCTDUMP.
      * Prints one line per account: id, status, balance, credit limit.
      * Replacement for CBACT01C, which stops after the first record on
      * GnuCOBOL because it calls the z/OS assembler module COBDATFT.
      * Optional argument: a single 11-digit account id to show.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ACCTFILE-FILE ASSIGN TO ACCTFILE
                  ORGANIZATION IS INDEXED
                  ACCESS MODE  IS SEQUENTIAL
                  RECORD KEY   IS FD-ACCT-ID
                  FILE STATUS  IS ACCTFILE-STATUS.
       DATA DIVISION.
       FILE SECTION.
       FD  ACCTFILE-FILE.
       01  FD-ACCTFILE-REC.
           05 FD-ACCT-ID                        PIC 9(11).
           05 FD-ACCT-DATA                      PIC X(289).
       WORKING-STORAGE SECTION.
       01  ACCTFILE-STATUS   PIC XX.
       01  WS-WANT           PIC X(11) VALUE SPACES.
       01  WS-EOF            PIC X VALUE 'N'.
       COPY CVACT01Y.
       01  WS-BAL            PIC -9(10).99.
       01  WS-LIM            PIC -9(10).99.
       PROCEDURE DIVISION.
           ACCEPT WS-WANT FROM COMMAND-LINE
           OPEN INPUT ACCTFILE-FILE
           PERFORM UNTIL WS-EOF = 'Y'
               READ ACCTFILE-FILE INTO ACCOUNT-RECORD
                   AT END MOVE 'Y' TO WS-EOF
               END-READ
               IF WS-EOF = 'N'
                  IF WS-WANT = SPACES OR WS-WANT = ACCT-ID
                     MOVE ACCT-CURR-BAL     TO WS-BAL
                     MOVE ACCT-CREDIT-LIMIT TO WS-LIM
                     DISPLAY ACCT-ID ' ' ACCT-ACTIVE-STATUS
                             ' BAL ' WS-BAL ' LIMIT ' WS-LIM
                  END-IF
               END-IF
           END-PERFORM
           CLOSE ACCTFILE-FILE
           STOP RUN.
