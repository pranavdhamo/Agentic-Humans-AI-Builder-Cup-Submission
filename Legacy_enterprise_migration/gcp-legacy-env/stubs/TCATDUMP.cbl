       IDENTIFICATION DIVISION.
       PROGRAM-ID. TCATDUMP.
      * Prints the transaction-category balance file: account, type, category, balance.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT TCATBALF-FILE ASSIGN TO TCATBALF
                  ORGANIZATION IS INDEXED
                  ACCESS MODE  IS SEQUENTIAL
                  RECORD KEY   IS FD-TRAN-CAT-KEY
                  FILE STATUS  IS TCATBALF-STATUS.
       DATA DIVISION.
       FILE SECTION.
       FD  TCATBALF-FILE.
       01  FD-TRAN-CAT-BAL-RECORD.
           05 FD-TRAN-CAT-KEY.
              10 FD-TRANCAT-ACCT-ID             PIC 9(11).
              10 FD-TRANCAT-TYPE-CD             PIC X(02).
              10 FD-TRANCAT-CD                  PIC 9(04).
           05 FD-FILLER                         PIC X(33).
       WORKING-STORAGE SECTION.
       01  TCATBALF-STATUS   PIC XX.
       01  WS-EOF            PIC X VALUE 'N'.
       COPY CVTRA01Y.
       01  WS-BAL            PIC -9(09).99.
       PROCEDURE DIVISION.
           OPEN INPUT TCATBALF-FILE
           PERFORM UNTIL WS-EOF = 'Y'
               READ TCATBALF-FILE INTO TRAN-CAT-BAL-RECORD
                   AT END MOVE 'Y' TO WS-EOF
               END-READ
               IF WS-EOF = 'N'
                  MOVE TRAN-CAT-BAL TO WS-BAL
                  DISPLAY TRANCAT-ACCT-ID ' ' TRANCAT-TYPE-CD ' '
                          TRANCAT-CD ' BAL ' WS-BAL
               END-IF
           END-PERFORM
           CLOSE TCATBALF-FILE
           STOP RUN.
