# Agentic Humans: AI Builder Cup submission

**Migration Studio**: Gemini ports mainframe COBOL to Java Spring Batch, and every output record is checked against what the real COBOL produced. The expected output comes from running the original program under GnuCOBOL, never from a model.

Everything lives in [`Legacy_enterprise_migration/`](Legacy_enterprise_migration/):

| Path | What it is |
|---|---|
| `oracle/`, `verifier/`, `pipeline/`, `migrated/`, `gcp-legacy-env/` | the proof: COBOL oracle, differential verifier, Gemini generate -> verify -> repair loop, reference Java ports, the legacy COBOL environment on GCP |
| `server/` | FastAPI backend: sign-in, roles, projects, Gemini provider admin, jobs, human review gates, live streaming |
| `client/` | React + TypeScript + Tailwind studio: decision tree, human-in-the-loop gates, n8n-style orchestration board, admin and IAM, light and dark theme |
| `cicd/` | GitHub Actions, Cloud Build, Dockerfiles, docker-compose, dev scripts |

## Run it
```bash
cd Legacy_enterprise_migration
(cd migrated/carddemo-batch && mvn -B package)   # build + parity tests
python verifier/check_all.py                     # expect: ALL SCENARIOS PASS
bash cicd/scripts/dev.sh                         # studio: UI :5173, API :8000 (Windows: powershell -File cicd\scripts\dev.ps1)
```
Demo logins (seeded locally, change before sharing): `admin@studio.local` / `admin123`; `architect@`, `senior@`, `junior@`, `intern@studio.local` / `studio123`.
Full instructions: [BOOTUP.md](Legacy_enterprise_migration/BOOTUP.md). Architecture: [architecture.md](Legacy_enterprise_migration/architecture.md). Summary: [summarize.md](Legacy_enterprise_migration/summarize.md).

CI runs from `.github/workflows/ci.yml`. The Cloud Run deploy workflow is opt-in: copy `Legacy_enterprise_migration/cicd/github-workflows/cd.yml` into `.github/workflows/` after the GCP setup in `cicd/README.md`.

COBOL source: `aws-samples/aws-mainframe-modernization-carddemo` (Apache-2.0), fetched at a pinned commit, not vendored.
