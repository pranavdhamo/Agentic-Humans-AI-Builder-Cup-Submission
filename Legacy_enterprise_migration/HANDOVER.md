# Handover: COBOL -> Java migration proof (legacy migration track)

## What exists
CardDemo's COBOL batch programs run under GnuCOBOL (the "oracle"). Two of them are ported to Java Spring Batch by hand
(reference ports) **and** by Gemini through a generate -> verify -> repair loop. Every claim is checked by diffing each output
record against what the real COBOL produced. See `MIGRATION_PIPELINE.md` for the architecture and commands.

| Program | COBOL | Java package | Scenarios (all match the COBOL) |
|---|---|---|---|
| Daily transaction posting | `CBTRN02C` | `posttran` | sample, edge (122 txns), hidden-state |
| Monthly interest | `CBACT04C` | `intcalc` | sample, interest-edge, abend-account, abend-xref, abend-rate |

## Results (Gemini, `gemini-3.8-flash`, temperature 0.2)
See `pipeline/RESULTS.md` (generated) and the raw reports in `pipeline/results/`.
- Posting: first attempt got every business rule right; the only miss was COBOL's hidden working-storage state on newly
  created category records (filler inherited from the last record read). One repair fixed it.
- The first "PASS" was a false pass (hard-coded zero filler). A scenario built to expose that caught it; after it was added the
  model implemented the real mechanism and diagnosed it correctly.
- Interest: passed first time (guided and naive), including the legacy "last account never settled" bug and the abend paths.
- The COBOL-semantics primer made no measurable difference in these runs (n = 1 per setting; indicative only).
- Cost: about 13K-29K tokens in and 5K-9K out per migration, 3-7 minutes of model time.

## Conditions under which this was produced
| | |
|---|---|
| Machine | macOS (Apple silicon, arm64) laptop, not the GCP VM |
| COBOL runtime | GnuCOBOL 3.2.0 (`brew install gnucobol`) with `-fsign=EBCDIC` (see `gcp-legacy-env/`) |
| COBOL source | `aws-samples/aws-mainframe-modernization-carddemo` @ `59cc6c2` (Apache-2.0), batch programs only, VSAM replaced by GnuCOBOL indexed files |
| Java / build | OpenJDK 27 compiling with `--release 21`, Maven 3.10.0, Spring Boot 3.5.16 (Spring Batch 5), H2 for job metadata only |
| Python | 3.13; `google-genai` 2.31.0 in `pipeline/.venv` |
| Model | `gemini-3.8-flash` via the Gemini API (AI Studio key in a git-ignored `.env`), temperature 0.2, 10-minute request cap, retry on 429/5xx/network errors |
| Runs | 5 migration runs on 18 Oct 2026, one per setting, so results are indicative, not statistics |
| Determinism | clock fields (processed timestamps) are masked by the verifier; everything else must match byte for byte |

Not covered: online CICS screens, Db2/IMS/MQ variants, `CBSTM03A/B`, `CBEXPORT/CBIMPORT` (they need a mainframe runtime).

## Replicate on the GCP VM (untested: written from reading the scripts, nobody has run it there yet)
The VM from `gcp-legacy-env/` (Debian 12, GnuCOBOL built by `provision.sh`, CardDemo cloned and compiled under
`/opt/carddemo-env`) already holds the oracle half. See `gcp-legacy-env/RESTART-VM.md` to start it.
```bash
# on the VM
sudo apt-get update && sudo apt-get install -y git maven python3-venv python3-pip
# JDK: the project targets Java 21 (pom.xml). Debian 12 ships 17 by default: install a 21 JDK (e.g. Temurin or bookworm-backports).
git clone <repo-url> && cd AI_builder_cup && git checkout pranav/migration-pipeline && cd Legacy_enterprise_migration

export BASE=/opt/carddemo-env SRC=/opt/carddemo-env/carddemo/app     # where provision.sh put things
sudo -E env "PATH=$PATH" oracle/make_scenarios.sh                       # /opt is root-owned; or chown it to your user
git diff --stat oracle/golden                                           # expect ONLY timestamp bytes in TRANSACT.flat / SYSTRAN.ps:
                                                                        # that proves the Mac and the VM COBOL agree

(cd migrated/carddemo-batch && mvn -q package)                          # build + JUnit parity tests
python3 verifier/check_all.py                                           # every scenario: PASS
python3 -m venv pipeline/.venv && pipeline/.venv/bin/pip install -r pipeline/requirements.txt
export GEMINI_API_KEY=...                                               # from Secret Manager; never commit it
pipeline/.venv/bin/python pipeline/migrate.py --program posttran --model gemini-3.8-flash
```
Gotchas: `JAVA_HOME` is honoured by the scripts (falls back to Homebrew's OpenJDK on macOS, else `PATH`); the `.so`/`.dylib`
shim in `run_oracle.sh` only runs on macOS; keep the key out of the repo (`.env` is git-ignored).

## What's left for the team
**Verify and deploy**
1. Run the VM steps above and confirm `oracle/golden` is unchanged except timestamps (cross-platform proof).
2. Decide how the pipeline authenticates on GCP: the AI Studio key (Secret Manager) or Vertex AI with a service account.
   `pipeline/llm.py` currently uses the API-key client; a Vertex client would be a small change (check the SDK docs).
3. CI: Cloud Build job running `mvn package` and `python3 verifier/check_all.py` on every push.

**Demo / product**
4. UI (not started): FastAPI wrapper over `pipeline/migrate.py` plus a React dashboard. Suggested panels: convergence curve per
   attempt, scenarios x artifacts verification matrix with record-level diffs, COBOL <-> Java side by side with extracted
   rules, a "preserve vs fix the last-account interest bug" toggle, human-review queue (low confidence -> ticket assigned by
   skill, as in the team notes).
5. More measurement for the pitch: several runs per setting, a naive "paste into the model" baseline per program, optionally a
   Pro-tier ceiling run; report tokens and wall-clock against a manual estimate.

**Coverage**
6. Port and verify the remaining runnable programs: `CBTRN01C`, `CBTRN03C` (report), `CBACT01C-03C`, `CBCUS01C`.
7. Close known test gaps: reject reason 101 (account missing during posting) needs a custom initial state; interest with two
   cards per account (alternate-key duplicates); let Gemini propose extra edge cases, still judged by the real COBOL.
8. Data migration: VSAM files -> Cloud SQL / AlloyDB, with a row-by-row equality check against the COBOL files.
9. Online (CICS/BMS) screens -> Spring MVC. The oracle cannot run them, so they need a different verification story.

**Housekeeping**
10. `README.md` and `Readme.md` both exist in the repo root; macOS treats them as one file and shows a phantom modification.
    Delete or merge one. Do not `git add -A` blindly.
11. The root `.gitignore` now ignores `.env`, `.env.*` (except `.env.example`). Keep the key out of the repo.
12. `POC_Predictive_Maintenance.md` and the rest of `backend/`, `frontend/` belong to a different track and were not touched.
