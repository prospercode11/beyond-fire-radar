#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python3 -m ruff format --check apps/api scripts
python3 -m ruff check apps/api scripts
python3 -m mypy apps/api/app
python3 -m pytest
npm --prefix apps/web run lint
npm --prefix apps/web run build

echo "Verification passed. Start the API separately before running scripts/dev.py api-smoke."
