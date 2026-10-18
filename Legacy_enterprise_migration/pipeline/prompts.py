"""Prompt construction for generate / repair. Kept separate so prompts are reviewable and diffable."""

SYSTEM = (
    "You are a senior mainframe-modernization engineer migrating an IBM COBOL batch program to Java 21 / Spring Boot 3 / "
    "Spring Batch 5. Your Java must reproduce the COBOL program's observable behaviour EXACTLY, byte for byte, "
    "including its quirks and bugs, because it will be verified by running the original COBOL and diffing every output "
    "record. Do not 'fix' or 'improve' legacy behaviour. Never hard-code test data. Reply with a single JSON object."
)

# Generic COBOL semantics - deliberately NOT specific to any program. Included in 'guided' mode only.
PRIMER = """\
COBOL SEMANTICS THAT COMMONLY BREAK TRANSLATIONS (apply them where relevant):
- Signed DISPLAY numbers (PIC S9(n)V99) carry the sign in the LAST character (overpunch): '{'=+0, 'A'-'I'=+1..+9,
  '}'=-0, 'J'-'R'=-1..-9. Use CobolNumeric.decodeSigned / encodeSigned.
- Arithmetic (ADD / COMPUTE) WITHOUT ROUNDED truncates extra decimals toward zero, and silently drops overflowing
  high-order digits (no exception). Use CobolNumeric.fit(value, integerDigits, scale) after every arithmetic store into a
  fixed-size field. Never use HALF_UP / default rounding.
- Statements execute strictly one record at a time: validation of record N sees all updates made by record N-1. Do not
  defer state updates to an ItemWriter.
- IF without ELSE: later IF statements still run and may OVERWRITE results set by earlier ones. Preserve statement order
  exactly; do not turn sequential IFs into else-if chains.
- WORKING-STORAGE record buffers keep their previous contents: a READ ... INTO only overwrites the buffer when the read
  succeeds; INITIALIZE does not touch FILLER items. Data can therefore leak from one record into the next.
- A keyed READ ... INVALID KEY with no abend handling just continues; a status-check ELSE that PERFORMs 9999-ABEND-PROGRAM
  ends the whole run immediately (work already written stays written, return code 16 in this environment).
- Alphanumeric comparisons (ISO dates as text, keys) compare characters left to right; numeric DISPLAY items compare by value.
- Indexed (VSAM) files return records in primary-key order. Sequential files are fixed-length with no line breaks.
- Unreachable code stays unreachable: if a paragraph can never execute in the COBOL, the Java must not execute it either.
"""

CONTRACT = """\
OUTPUT CONTRACT (the verifier relies on it):
- Put ALL files under src/main/java/com/agentichumans/carddemo/{pkg}/ , package com.agentichumans.carddemo.{pkg}.
  The shared library in package com.agentichumans.carddemo.cobol (shown below) already exists - import it, do not redefine it.
- Provide Spring @Configuration class(es) conditional on @ConditionalOnProperty(name = "carddemo.job", havingValue = "{pkg}")
  that define exactly one org.springframework.batch.core.Job bean and exactly one bean implementing
  com.agentichumans.carddemo.cobol.RunResult (returnCode() = the COBOL RETURN-CODE, summary() = counters text).
- Read inputs and write outputs ONLY through these Spring properties (use @Value):
{properties}
- Output files (same names, same fixed-width record layouts as the COBOL files, ISO-8859-1, no line separators between
  records, written when the job finishes - also when the COBOL would have abended):
{outputs}
- Fields that come from the system clock (timestamps) are masked by the verifier; use java.time.LocalDateTime.now().
- Use Spring Batch chunk-oriented or tasklet steps as you see fit. It must run with: java -jar carddemo-batch.jar --carddemo.job={pkg}
- Do not use any dependency beyond what pom.xml already provides (spring-boot-starter-batch, H2).
"""

GENERATE = """\
{contract}

{primer}
=== COBOL PROGRAM {program_name} ({cobol_file}) ===
{cobol}

=== COPYBOOKS IT USES ===
{copybooks}

=== SHARED JAVA LIBRARY (package com.agentichumans.carddemo.cobol) ===
{library}

TASK: write the Java port. Reply as JSON: {{"files": {{"<relative path from project root>": "<full file content>"}},
"rules": ["<each business rule you identified, one line, citing the COBOL paragraph>"], "notes": "<assumptions>"}}
"""

REPAIR = """\
{contract}

{primer}
Your previous Java port was built and verified by running the ORIGINAL COBOL program and diffing every output record.
It is NOT yet identical. Fix the defects in your code so that the output matches the COBOL exactly.

=== COBOL PROGRAM {program_name} ===
{cobol}

=== YOUR CURRENT JAVA FILES ===
{current}

=== VERIFICATION RESULT (iteration {iteration}) ===
{failures}

Rules for the fix: change the logic, never special-case the failing records or hard-code expected values; keep legacy
behaviour even when it looks like a bug. Reply as JSON with the COMPLETE content of every file you change or keep:
{{"files": {{"<path>": "<full file content>"}}, "diagnosis": "<root cause of each mismatch group>", "notes": ""}}
"""
