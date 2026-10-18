#!/usr/bin/env bash
# GitHub only runs workflows from <repo root>/.github/workflows. Copy ours there.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(git -C "$HERE" rev-parse --show-toplevel)"
mkdir -p "$REPO_ROOT/.github/workflows"
cp "$HERE/../github-workflows/"*.yml "$REPO_ROOT/.github/workflows/"
echo "Installed: $(ls "$REPO_ROOT/.github/workflows" | tr '\n' ' ')"
