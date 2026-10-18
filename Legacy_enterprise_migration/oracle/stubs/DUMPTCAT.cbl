       IDENTIFICATION DIVISION.
       PROGRAM-ID. DUMPTCAT.
      * Dumps every raw 50-byte transaction-category-balance record,
      * in key order, to a flat file (DD_FLATOUT).
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT TCAT-IN ASSIGN TO TCATBALF
                  ORGANIZATION IS INDEXED
                  ACCESS MODE  IS SEQUENTIAL
                  RECORD KEY   IS IN-KEY
                  FILE STATUS  IS IN-ST.
           SELECT FLAT-OUT ASSIGN TO FLATOUT
                  ORGANIZATION IS SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  TCAT-IN.
       01  IN-REC.
           05 IN-KEY                  PIC X(17).
           05 IN-REST                 PIC X(33).
       FD  FLAT-OUT.
       01  OUT-REC                    PIC X(50).
       WORKING-STORAGE SECTION.
       01  IN-ST                      PIC XX.
       01  WS-EOF                     PIC X VALUE 'N'.
       PROCEDURE DIVISION.
           OPEN INPUT TCAT-IN OUTPUT FLAT-OUT
           PERFORM UNTIL WS-EOF = 'Y'
               READ TCAT-IN AT END MOVE 'Y' TO WS-EOF END-READ
               IF WS-EOF = 'N'
                  MOVE IN-REC TO OUT-REC
                  WRITE OUT-REC
               END-IF
           END-PERFORM
           CLOSE TCAT-IN FLAT-OUT
           STOP RUN.
