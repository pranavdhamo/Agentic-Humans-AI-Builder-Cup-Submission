# CI/CD

| File | Purpose |
|---|---|
| `github-workflows/ci.yml` | 5 gated jobs on every push/PR: **parity** (JUnit + `check_all.py` + mutation check) -> **pipeline-mock** (full generate/verify/repair loop, no API key) and **server** (ruff + pytest) -> **client** (typecheck + vitest + build) -> **images** (both Docker builds) |
| `github-workflows/cd.yml` | On green `main`: build, push to Artifact Registry, deploy `studio-server` and `studio-client` to Cloud Run, smoke test |
| `cloudbuild.yaml` | Same gate on Cloud Build for teams that stay inside GCP |
| `docker/` | `Dockerfile.server` (JDK 21 + Maven + Python + CardDemo source), `Dockerfile.client` (Vite build served by nginx, proxies `/api` with SSE unbuffered) |
| `docker-compose.yml` | Whole studio locally: UI :8080, API :8000, a volume for users, projects and the encrypted provider key |
| `scripts/dev.sh`, `scripts/dev.ps1` | One-command local bootup (creates venv, installs, builds the jar) |
| `scripts/install-workflows.sh` | Copies the workflows to `<repo root>/.github/workflows` (GitHub only reads that location) |

The gate that matters is **parity**: a change that makes the Java ports drift from the COBOL golden output fails the build.

## Use it
```bash
bash cicd/scripts/install-workflows.sh      # once, then commit .github/
docker compose -f cicd/docker-compose.yml up --build
```

## One-time GCP setup for `cd.yml`
```bash
gcloud services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
gcloud artifacts repositories create studio --repository-format=docker --location=us-central1
printf '%s' "$GEMINI_API_KEY" | gcloud secrets create gemini-api-key --data-file=-
```
Then create a Workload Identity Federation provider for the GitHub repo and a service account with
`run.admin`, `artifactregistry.writer`, `iam.serviceAccountUser` and `secretmanager.secretAccessor`.
Set repository variables `GCP_PROJECT`, `GCP_REGION`, `AR_REPO` (= `studio`) and secrets `WIF_PROVIDER`, `WIF_SERVICE_ACCOUNT`.

## Secrets
Set `STUDIO_SECRET` (signs sessions, derives the key-encryption key), `STUDIO_ADMIN_PASSWORD` and `STUDIO_DEMO_PASSWORD` in the environment
(Cloud Run: Secret Manager) before the first start; otherwise the seeded demo passwords apply. The Gemini key is entered by the admin in the UI
and stored encrypted in the studio database; `GEMINI_API_KEY` in the environment is only a fallback.

## Caveats
- Job history is in memory; users, projects, boards, usage and the audit log are in SQLite under `server/data` (mount a persistent volume).
- Cloud Run instances are ephemeral and the job log is in memory: runs stored under `pipeline/runs` are lost on restart. Fine for a demo; mount a bucket for persistence.
- Only one job runs at a time (shared Maven target and golden files), so `--max-instances 1` is deliberate.
- `ci.yml` and `cd.yml` have not been executed on GitHub yet; the commands inside them were each run locally.
