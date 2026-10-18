       IDENTIFICATION DIVISION.
       PROGRAM-ID. DUMPACCT.
      * Dumps every raw 300-byte account record, in key order, to a
      * flat file (DD_FLATOUT). Used to capture final account state.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ACCT-IN ASSIGN TO ACCTFILE
                  ORGANIZATION IS INDEXED
                  ACCESS MODE  IS SEQUENTIAL
                  RECORD KEY   IS IN-KEY
                  FILE STATUS  IS IN-ST.
           SELECT FLAT-OUT ASSIGN TO FLATOUT
                  ORGANIZATION IS SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  ACCT-IN.
       01  IN-REC.
           05 IN-KEY                  PIC X(11).
           05 IN-REST                 PIC X(289).
       FD  FLAT-OUT.
       01  OUT-REC                    PIC X(300).
       WORKING-STORAGE SECTION.
       01  IN-ST                      PIC XX.
       01  WS-EOF                     PIC X VALUE 'N'.
       PROCEDURE DIVISION.
           OPEN INPUT ACCT-IN OUTPUT FLAT-OUT
           PERFORM UNTIL WS-EOF = 'Y'
               READ ACCT-IN AT END MOVE 'Y' TO WS-EOF END-READ
               IF WS-EOF = 'N'
                  MOVE IN-REC TO OUT-REC
                  WRITE OUT-REC
               END-IF
           END-PERFORM
           CLOSE ACCT-IN FLAT-OUT
           STOP RUN.
