       IDENTIFICATION DIVISION.
       PROGRAM-ID. TRANFLAT.
      * Emulates the REPRO step of TRANREPT.jcl: copies the indexed
      * transaction file (TRANFILE) to a flat sequential file (FLATOUT).
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT TRANFILE-FILE ASSIGN TO TRANFILE
                  ORGANIZATION IS INDEXED
                  ACCESS MODE  IS SEQUENTIAL
                  RECORD KEY   IS FD-TRANS-ID
                  FILE STATUS  IS TRANFILE-STATUS.
           SELECT FLAT-FILE ASSIGN TO FLATOUT
                  ORGANIZATION IS SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  TRANFILE-FILE.
       01  FD-TRANFILE-REC.
           05 FD-TRANS-ID                       PIC X(16).
           05 FD-TRANS-DATA                     PIC X(334).
       FD  FLAT-FILE.
       01  FLAT-REC                             PIC X(350).
       WORKING-STORAGE SECTION.
       01  TRANFILE-STATUS   PIC XX.
       01  WS-EOF            PIC X VALUE 'N'.
       PROCEDURE DIVISION.
           OPEN INPUT TRANFILE-FILE OUTPUT FLAT-FILE
           PERFORM UNTIL WS-EOF = 'Y'
               READ TRANFILE-FILE
                   AT END MOVE 'Y' TO WS-EOF
               END-READ
               IF WS-EOF = 'N'
                  MOVE FD-TRANFILE-REC TO FLAT-REC
                  WRITE FLAT-REC
               END-IF
           END-PERFORM
           CLOSE TRANFILE-FILE FLAT-FILE
           STOP RUN.
