# Architecture

## Tech stack
| Layer | Technology |
|---|---|
| Legacy runtime ("oracle") | GnuCOBOL 3.2, compiled with `-fsign=EBCDIC`; VSAM replaced by GnuCOBOL indexed files |
| Legacy hosting | GCP Compute Engine e2-medium, Debian 12, provisioned by shell scripts and `gcloud` |
| COBOL source | `aws-samples/aws-mainframe-modernization-carddemo` @ `59cc6c2` (Apache-2.0), batch programs only |
| Target app | Java 21, Spring Boot 3.5.16, Spring Batch 5, H2 (job metadata only), Maven |
| Tests | JUnit 5 via `spring-boot-starter-test` (`ParityTest`) |
| Verifier / pipeline | Python 3.11+ (3.13 used), standard library only for the verifier |
| Studio API | FastAPI, uvicorn, Pydantic v2, Server-Sent Events, pytest, ruff |
| Studio UI | React 18, TypeScript, Tailwind CSS 3, Vite 5, React Router, Vitest |
| CI/CD | GitHub Actions, Cloud Build, Docker + nginx, Cloud Run, Artifact Registry |
| LLM | Google Gemini (`gemini-3.8-flash`, temperature 0.2) through the `google-genai` SDK and an AI Studio API key |
| Scenario generation | Python scripts (`oracle/gen_*.py`) plus bash (`make_scenarios.sh`, `run_oracle.sh`) |

## System overview
```
                    ORACLE (ground truth)                          MIGRATION + PROOF
 CardDemo COBOL ──► GnuCOBOL run per scenario ──► oracle/golden/ ──┐
 + copybooks            (run_oracle.sh)           (flat files)     │
        │                                                           ▼
        │                                                   verifier/verify.py
        │                                                  field-level diff by key
        ▼                                                           ▲
 pipeline/migrate.py ─► prompts + COBOL ─► Gemini ─► Java files ─► mvn package ─► run on scenario inputs
        ▲                                                                              │
        └──────────── mismatches formatted as repair prompt ◄──────── report ◄─────────┘
```

## Components

### `gcp-legacy-env/`: the "before" system
`provision.sh` creates the VM, `bootstrap-vm.sh` builds GnuCOBOL and clones CardDemo, `build.sh` compiles the programs,
`load-data.sh` replaces IDCAMS/REPRO by loading data into indexed files, `run-batch.sh` runs POSTTRAN then INTCALC.
JCL DD names map to `DD_<name>` env vars. `stubs/` replaces the IBM Language Environment abend call (`CEE3ABD`) and
supplies the JCL PARM for CBACT04C.

### `oracle/`: golden output
- `run_oracle.sh` reloads data from scratch (the COBOL mutates its own files), runs the stages, and snapshots outputs to `golden/<scenario>/`.
- `gen_edge_cases.py`, `gen_interest_cases.py`, `gen_state_cases.py` build targeted initial states and transactions (boundaries, overflow, expiry, abends, hidden state).
- `stubs/DUMPACCT.cbl`, `DUMPTCAT.cbl` dump final account and category state as raw records.
- Each scenario folder holds `input/`, the output flat files, `rc.txt` and `stdout.txt`; `scenarios/*/cases.json` documents the cases.

### `migrated/carddemo-batch/`: reference Java ports
Package `com.agentichumans.carddemo` (about 720 lines):
- `cobol/`: `CobolNumeric` (signed overpunch, truncation, wrap), `FixedRecordReader`, `Records` (fixed-width layouts), `RunResult`
- `posttran/`: `PostTranJobConfig`, `PostTranProcessor`, `Ledger`, `RunState` (CBTRN02C)
- `intcalc/`: `InterestJobConfig`, `InterestProcessor`, `InterestLedger`, `InterestState` (CBACT04C)
- `CardDemoApplication`: Spring Boot entry; web server off, batch auto-run off, job metadata in embedded H2
- Paths are set by `carddemo.*` properties; `carddemo.intcalc.fix-last-account` toggles legacy-bug preservation

The design is a Spring Batch chunk pipeline: a reader parses fixed-width records, a processor applies the COBOL rules
over an in-memory ledger that mirrors the VSAM files, and a writer emits fixed-width files byte-compatible with COBOL.

### `verifier/`
- `verify.py`: layouts from the copybooks as (name, offset, length) tuples; aligns records by key, compares field by field, masks the processed-timestamp, emits a JSON report. Exit 0 means identical, 1 means mismatches. No LLM involved.
- `scenarios.py`: scenario registry; `check_all.py` runs every program on every scenario.
- `mutation_check.py`: applies 27 plausible bugs to the Java port and requires the verifier to catch each one.

### `pipeline/`: Gemini loop
- `migrate.py`: builds a workspace, extracts COBOL and copybooks from the CardDemo checkout, calls the provider, writes the returned files, runs `mvn package`, runs every scenario, summarizes, and builds the repair prompt. Options: `--program`, `--provider gemini|mock`, `--mode guided|naive`, `--max-repairs`, `--model`.
- `llm.py`: `GeminiProvider` (retry on 429/5xx/network errors, 10-minute request cap, JSON answers) and `MockProvider` (scripted replay for offline loop testing).
- `prompts.py`: generate and repair prompts plus the optional COBOL-semantics primer (`guided` mode).
- `mock_versions.py`: the scripted answers; `results.py`: renders `RESULTS.md` from `results/*/report.json`.
- Each run records, per attempt: build status, scenarios passed, records identical, tokens in and out.

### `server/`: Studio API (FastAPI + SQLite)
- **Auth** (`security.py`, `deps.py`, `routers/auth.py`): PBKDF2 passwords, HMAC-signed 12h session tokens (`?token=` for EventSource), Fernet encryption for provider keys. Every route except `/api/health` needs a signed-in user.
- **IAM** (`db.py`, `policy.py`, `routers/admin.py`): users, teams, projects (assigned to users and teams), role policies, the Gemini provider, usage and audit tables. Roles: project_admin, lead_architect, senior_dev, junior_dev, intern. A policy is data: providers, model tier, max repairs, prompt modes, allowed agents, permissions, runs per day, token budget.
- **Enforcement** (`services/authz.py`): starting a migration checks project membership, provider and model tier, repairs, agents (gates), then daily user, team and total project token budgets. All reasons are returned together as a 403. Usage is recorded when a run finishes.
- **Jobs** (`jobs.py`, `routers/jobs.py`): one background job at a time (shared Maven target and golden files). Kinds: `build`, `verify` (in-process loop over `verifier/scenarios.py`), `migrate` (subprocess of `pipeline/migrate.py`), `mutation`. Append-only event log streamed over SSE.
- **Studio protocol**: `migrate.py` prints `@@STEP` (llm, build, verify, decision), `@@GATE` and `@@GATE_DONE` lines. The server turns them into `step`, `gate`, `gate_done` events. A gate pauses the run: `migrate.py` waits for `response-<id>.json` in a per-job temp dir, written by `POST /api/jobs/{id}/gate` (needs `can_approve_gates`). A reviewer hint is appended to the generate or repair prompt; "stop" ends the run (`stopped_by_reviewer` in the report); a timeout also stops it.
- **Board** (`services/board.py`, `routers/projects.py`): the per-project node graph is validated and compiled into the migrate parameters; running a board starts a normal migration, so the same policy checks apply.
- **Catalog and runs** (`services/catalog.py`, `services/runs.py`): scenarios, golden records parsed with the verifier's layouts, COBOL and Java source, run history. Fresh runs are visible only to members of the owning project; curated results are visible to everyone.
- Tests: 22 pytest tests including live pipeline tests (verify job, human gate pause/approve/stop, project-scoped run visibility).

### `client/`: Studio UI (React 18, TypeScript, Tailwind, Vite, React Flow)
`ThemeProvider` (CSS-variable palette, light and dark), `AuthProvider` (session, profile, active project) and `JobProvider` (follows the active job over `EventSource`, derives logs, attempts, steps and the pending gate) wrap the app. Pages: Dashboard, Migration Studio (config limited by the role's policy, decision tree, human gate panel, convergence chart), Orchestrator (React Flow board, node inspector, compiled plan, live node status, locked agents), Verifier, Run History, Oracle Explorer, Admin and IAM. Vite proxies `/api` in dev; nginx does in the container.

### `cicd/`
GitHub Actions `ci.yml` (parity gate, mock migration loop, server, client, image builds) and `cd.yml` (Cloud Run), `cloudbuild.yaml`, Dockerfiles, compose and dev scripts. See `cicd/README.md`.

## Data flow for one migration run
1. Load COBOL source and copybooks for the chosen program.
2. Prompt Gemini for a complete Spring Batch project as JSON `{files, notes}`.
3. Write files into a temp project, build with Maven.
4. Run the jar on each scenario's `input/`; collect output files.
5. `verify.py` compares them with `oracle/golden/<scenario>/`.
6. If anything differs and attempts remain, send the field-level diffs back and repeat from step 2.
7. Write `report.json` under `pipeline/runs/<id>/`; keep notable ones in `pipeline/results/`.

## Design principles
- **Ground truth is executed, not generated.** Expected output comes only from the real COBOL.
- **Differential, byte-level comparison** of fixed-width records, with only legitimately non-deterministic fields masked.
- **Adversarial scenarios.** Scenarios are built to expose shortcuts (hidden state, overflow, abends); the verifier is itself mutation-tested.
- **Secrets stay out of the repo.** The API key comes from the environment or a git-ignored root `.env`.
- **Reproducibility.** Pinned CardDemo commit, fixed temperature, golden files committed.

## Limits and extension points
- Only batch programs that GnuCOBOL can run are covered; CICS/BMS, Db2, IMS, MQ, `CBSTM03A/B` and `CBEXPORT/CBIMPORT` are out of scope.
- `llm.py` uses an API-key client; Vertex AI with a service account would be a small swap for GCP deployment.
- Planned: FastAPI wrapper and React dashboard over `migrate.py`, CI on Cloud Build, more programs, and VSAM to Cloud SQL/AlloyDB data migration with row-level equality checks.
