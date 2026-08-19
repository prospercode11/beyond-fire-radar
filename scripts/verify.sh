#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python_bin="${PYTHON_BIN:-python3}"
if [[ -x "$repo_root/.venv/bin/python" && -z "${PYTHON_BIN:-}" ]]; then
  python_bin="$repo_root/.venv/bin/python"
fi

"$python_bin" -m ruff format --check apps/api scripts desktop
"$python_bin" -m ruff check apps/api scripts desktop
"$python_bin" -m mypy apps/api/app desktop/backend_entrypoint.py
"$python_bin" -m pytest
npm --prefix apps/web run lint
npm --prefix apps/web run build
npm --prefix desktop run test

echo "Verification passed. Start the API separately before running scripts/dev.py api-smoke."
