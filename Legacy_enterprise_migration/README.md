# Legacy enterprise migration: COBOL -> Java, proven against the real COBOL

Migrates AWS CardDemo's batch COBOL programs to Java Spring Batch, with Gemini doing the migration in a
generate -> verify -> repair loop. The expected output always comes from **running the original COBOL**
(GnuCOBOL), never from a model, and every output record is diffed field by field.

```
 COBOL source + copybooks
        |                                 oracle/            real COBOL under GnuCOBOL -> golden output
        v                                 verifier/          field-level diff, records aligned by key
 pipeline/migrate.py  --generate-->  Java (Spring Batch)  --build/run-->  output files
        ^                                        |
        +------- field-level mismatches ---------+   (repair loop, until identical or out of attempts)
```

| Program | COBOL | Java package | Scenarios |
|---|---|---|---|
| Daily transaction posting | `CBTRN02C` | `posttran` | sample, edge, hidden-state |
| Monthly interest | `CBACT04C` | `intcalc` | sample, interest-edge, abend-account, abend-xref, abend-rate |

## Quick start
Needs JDK 21+, Maven 3.9+, Python 3.11+. From this folder:
```bash
(cd migrated/carddemo-batch && mvn -B package)   # build + JUnit parity tests
python verifier/check_all.py                     # expect: ALL SCENARIOS PASS
```
No COBOL runtime or API key is needed for this: golden output is committed in `oracle/golden/`.
For the offline pipeline, real Gemini runs, regenerating golden output and the GCP VM, see **[BOOTUP.md](BOOTUP.md)**.

## Migration Studio (web UI)
An AI studio over the oracle, pipeline and verifier, with sign-in, roles and projects.
```bash
bash cicd/scripts/dev.sh                 # Windows: powershell -File cicd\scripts\dev.ps1
# UI http://localhost:5173    API docs http://localhost:8000/docs
```
Demo logins (seeded on first start; change them under Admin): `admin@studio.local` / `admin123`, and
`architect@`, `senior@`, `junior@`, `intern@studio.local` / `studio123`.

| Feature | What it does |
|---|---|
| **Migration Studio** | Start a Gemini or mock migration. A live **decision tree** (generate, build, compiles?, verify, all match?, repair...) grows as the run progresses |
| **Human in the loop** | Optional review gates before the first generation and before each repair. A reviewer approves, adds guidance that is injected into the model prompt, or stops the run |
| **Orchestrator** | n8n-style board (React Flow): drag, wire and configure the agents. It compiles to a real run (program, provider, model, repairs, gates) and shows live node status |
| **Roles and projects** | Project admin, lead architect, senior dev, junior dev, intern. Each role gets different agents, model tier, repair cap, daily runs and token budget; users only see projects they or their team are assigned to |
| **Admin and IAM** | Users, teams, projects, role policies, Gemini provider (API key stored encrypted, never returned), model tiers, usage and an audit log |
| **Light and dark theme** | Toggle in the header; follows the system setting by default |

| Folder | What it is |
|---|---|
| `client/` | React 18 + TypeScript + Tailwind (Vite) + React Flow |
| `server/` | FastAPI + SQLite. Auth, RBAC, jobs, human gates, SSE streaming |
| `cicd/` | GitHub Actions CI/CD, Cloud Build, Dockerfiles, docker-compose, dev scripts (see `cicd/README.md`) |

## Layout
| Path | What it is |
|---|---|
| `gcp-legacy-env/` | the "before" system: CardDemo batch COBOL on a GCP VM (GnuCOBOL); has its own README, `RESTART-VM.md`, `TESTING.md` |
| `oracle/` | runs scenarios through the real COBOL and stores golden output (`run_oracle.sh`, `make_scenarios.sh`, `gen_*_cases.py`) |
| `migrated/carddemo-batch/` | reference Java ports (Spring Boot 3.5, Spring Batch, H2 for job metadata) + JUnit parity tests |
| `verifier/` | `verify.py` (one run vs golden), `check_all.py` (all scenarios), `mutation_check.py` (27 deliberate breaks must all be caught) |
| `pipeline/` | Gemini loop (`migrate.py`, `llm.py`, `prompts.py`); results in `pipeline/RESULTS.md` |

## Results (Gemini `gemini-3.8-flash`, temperature 0.2, 5 runs, indicative only)
- Posting: every business rule right on the first attempt; one repair fixed COBOL's hidden working-storage state.
- Interest: passed first time, including the legacy "last account never settled" bug and the abend paths.
- About 13K-29K tokens in / 5K-9K out and 3-7 minutes per migration. Details: `pipeline/RESULTS.md`.

## Behaviours reproduced bug for bug
- Signed numbers keep the sign in the last character; arithmetic truncates and wraps on overflow.
- A transaction both over limit and expired is rejected as *expired* (a later IF overwrites the earlier one).
- New category-balance records inherit the filler of the last record read.
- The interest program never settles the last account's balance. Java preserves this;
  `--carddemo.intcalc.fix-last-account=true` applies the evident intent.
- Missing account, xref or default rate row abends the run (rc 16) and keeps work done so far.

## Not covered
CICS/BMS online screens, Db2/IMS/MQ variants, `CBSTM03A/B`, `CBEXPORT/CBIMPORT`. Reject reason 101 is not exercised.

## More docs
[BOOTUP.md](BOOTUP.md) (how to run) · [MIGRATION_PIPELINE.md](MIGRATION_PIPELINE.md) (architecture) ·
[HANDOVER.md](HANDOVER.md) (conditions and what's left) · [layman.md](layman.md) (plain-language overview)

COBOL source: `aws-samples/aws-mainframe-modernization-carddemo` @ `59cc6c2` (Apache-2.0).
