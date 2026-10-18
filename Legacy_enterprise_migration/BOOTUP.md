# Project bootup

Step-by-step to get this project running. Each level needs more tooling than the last; stop at the level you need.
Steps marked ✅ were run on Windows 11 (JDK 21, Maven 3.9.11, Python 3.13) and passed.

Run everything from `Legacy_enterprise_migration/` (Git Bash or WSL on Windows).

| Level | What you get | Needs |
|---|---|---|
| 1. Verify | Java ports checked against committed COBOL golden output | JDK 21, Maven, Python 3 |
| 2. Offline pipeline | The generate -> verify -> repair loop with a scripted mock "model" | Level 1 + a CardDemo checkout |
| 3. Real Gemini | Gemini actually migrates COBOL to Java | Level 2 + `GEMINI_API_KEY` |
| 4. Regenerate oracle | Re-run the real COBOL to rebuild golden output | Linux/macOS/WSL with GnuCOBOL 3.2 |
| 5. Legacy VM | The "before" system on GCP | gcloud + a GCP project |

## Prerequisites
- JDK 21+ (`java -version`), Maven 3.9+ (`mvn -v`), Python 3.11+ (`python --version`)
- Levels 2-3: `git`, and optionally a Gemini API key (Google AI Studio)
- Levels 4-5: WSL/Linux/macOS, GnuCOBOL 3.2 (`cobc`), and for level 5 the `gcloud` CLI

## Level 1: build and verify (no COBOL, no API key) ✅
```bash
# Build the Spring Batch project and run the JUnit parity tests
(cd migrated/carddemo-batch && mvn -B package)

# Check every program on every scenario against the COBOL golden output
python verifier/check_all.py
```
Expected: `ALL SCENARIOS PASS` with 8 rows (3 posttran, 5 intcalc).

Optional, takes a few minutes: `python verifier/mutation_check.py` breaks the Java port in 27 ways; every break must be caught.

To run a Java job by hand, see `ParityTest.java` and `src/main/resources/application.properties` for the
input/output property names (fixed-width COBOL record files; H2 is used only for job metadata).

## Level 2: offline pipeline with the mock provider ✅
The pipeline reads the original COBOL source and copybooks, so it needs a CardDemo checkout (public, Apache-2.0):
```bash
git clone https://github.com/aws-samples/aws-mainframe-modernization-carddemo ~/carddemo-env-local/carddemo
git -C ~/carddemo-env-local/carddemo checkout 59cc6c2          # commit used for the golden data

pip install -r pipeline/requirements.txt
# default location is ~/carddemo-env-local/carddemo/app; otherwise: export SRC=/path/to/carddemo/app
python pipeline/migrate.py --program intcalc --provider mock
```
Expected: build OK each round, scenarios go 0/5 -> 5/5, `VERDICT: PASS after 3 repair(s)`.
The mock is a scripted replay, **not a model**; it only proves the loop works. Reports are written to `pipeline/runs/<id>/report.json` (git-ignored).

## Level 3: real Gemini migration
```bash
export GEMINI_API_KEY=...        # PowerShell: $env:GEMINI_API_KEY = "..."
# or put the key in a git-ignored .env at the AI_builder_cup repo root (the root .gitignore already excludes .env)

python pipeline/migrate.py --program posttran --provider gemini --mode guided --model gemini-3.8-flash
python pipeline/migrate.py --program posttran --provider gemini --mode naive --max-repairs 0   # single-shot baseline
```
- `--program`: `posttran` (CBTRN02C) or `intcalc` (CBACT04C)
- `--mode guided` adds a COBOL-semantics primer; `naive` does not
- `--max-repairs N` (default 4); `0` = no repair loop
- Never commit the key. Past results: `pipeline/RESULTS.md`.

## Level 4: regenerate the golden output (needs real COBOL)
GnuCOBOL is not available on native Windows; use WSL (Ubuntu) or Linux/macOS.
```bash
sudo apt-get update && sudo apt-get install -y gnucobol     # macOS: brew install gnucobol
cobc --version                                               # expect 3.2
export BASE=~/carddemo-env-local SRC=~/carddemo-env-local/carddemo/app
oracle/make_scenarios.sh
git diff --stat oracle/golden      # only timestamp bytes may differ
```
Compilation uses `-fsign=EBCDIC` (see `gcp-legacy-env/build.sh`). Run a single scenario with `oracle/run_oracle.sh`.

## Level 5: the legacy COBOL environment on GCP
```bash
cd gcp-legacy-env
PROJECT_ID=<your-project> ./provision.sh                     # optional: ZONE=, VM=
gcloud compute ssh carddemo-legacy --command 'sudo /opt/carddemo-env/run-batch.sh'
gcloud compute instances stop carddemo-legacy                # stop when idle
```
Expect 300 posted / 38 rejected (rc=4 is the program's normal "had rejects" code). Restarting an existing VM: `gcp-legacy-env/RESTART-VM.md`.

## Web UI: Migration Studio (needs Level 1; migrations also need Level 2)
Needs Node 20+ (22 used) in addition to the Level 1 tools.
```bash
bash cicd/scripts/dev.sh                    # Windows: powershell -File cicd\scripts\dev.ps1
```
Or by hand, in two terminals:
```bash
# API  -> http://localhost:8000/docs
cd server && python -m venv .venv && .venv/bin/pip install -r requirements.txt     # Windows: .venv\Scripts\pip
export SRC=~/carddemo-env-local/carddemo/app                                        # only for migrations
.venv/bin/uvicorn app.main:app --port 8000

# UI   -> http://localhost:5173 (proxies /api to :8000)
cd client && npm install && npm run dev
```
Sign in (seeded demo accounts): `admin@studio.local` / `admin123`; `architect@`, `senior@`, `junior@`, `intern@studio.local` / `studio123`.
Then: **Verifier** > "Run all scenarios" streams the 8 scenarios live; **Migration Studio** > mock provider > tick
"before each repair" > "Start migration" pauses at a human gate (approve, add guidance, or stop) while the decision tree grows;
**Orchestrator** shows the saved pipeline board.

To use Gemini: sign in as the admin > **Admin and IAM > AI Providers**, paste the AI Studio key, set models and tiers, Save, then
"Test connection". Then set who may use it under **Role policies**, and assign people to projects under **Teams** and **Projects**.
The key is stored encrypted in `server/data/studio.db` (git-ignored) and injected only into the migration process.
Set `STUDIO_ADMIN_PASSWORD`, `STUDIO_DEMO_PASSWORD` and `STUDIO_SECRET` before the first start to avoid the demo defaults.
Whole stack in containers: `docker compose -f cicd/docker-compose.yml up --build` (UI :8080).

Checks: `cd server && pytest -q && ruff check .`, `cd client && npm run typecheck && npm test && npm run build`.

## Troubleshooting
| Symptom | Fix |
|---|---|
| `CardDemo source not found at ... (set SRC)` | Clone CardDemo (Level 2) or `export SRC=<checkout>/app` |
| `FileNotFoundError: [WinError 2]` from `migrate.py` | Fixed in this repo (`mvn` is `mvn.cmd` on Windows); make sure Maven is on `PATH` |
| `Set GEMINI_API_KEY ...` | Export the key or add it to the root `.env` |
| Wrong Java version | Point `JAVA_HOME` at a JDK 21+; the project compiles with `--release 21` |
| `cobc: command not found` | Only Level 4/5 need it; install GnuCOBOL in WSL/Linux |
| Verifier reports a mismatch | Expected for broken/mutated Java; the report lists record + field diffs |
