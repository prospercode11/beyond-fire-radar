#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python_bin="${PYTHON_BIN:-python3}"
if [[ -x "$repo_root/.venv/bin/python" && -z "${PYTHON_BIN:-}" ]]; then
  python_bin="$repo_root/.venv/bin/python"
fi

"$python_bin" -m pip check
if "$python_bin" -m pip_audit --version >/dev/null 2>&1; then
  audit_dir="$(mktemp -d "${TMPDIR:-/tmp}/bfr-dependency-audit.XXXXXX")"
  trap 'rm -rf "$audit_dir"' EXIT
  runtime_requirements="$audit_dir/runtime-requirements.txt"
  audit_report="$audit_dir/pip-audit.json"
  "$python_bin" -c 'from pathlib import Path; Path("'"$runtime_requirements"'").write_text("alembic\nboto3\nemail-validator\nfastapi\nhttpx\npsycopg[binary]\npython-multipart\npydantic-settings\nredis\nsqlalchemy\nuvicorn[standard]\n")'
  audit_status=0
  "$python_bin" -m pip_audit -r "$runtime_requirements" --strict --format=json --output="$audit_report" || audit_status=$?
  if [[ "$audit_status" -ne 0 ]]; then
    "$python_bin" - "$audit_report" <<'PY'
import json
import sys

allowed = {
    "PYSEC-2026-161", "PYSEC-2026-2280", "PYSEC-2026-2281", "PYSEC-2026-248", "PYSEC-2026-249",
    "PYSEC-2026-1852", "PYSEC-2026-3036", "PYSEC-2026-3037", "PYSEC-2026-3038", "PYSEC-2026-3039", "PYSEC-2026-3040",
    "PYSEC-2026-2270", "PYSEC-2026-2132", "PYSEC-2026-141", "PYSEC-2026-1999",
    "PYSEC-2026-1998", "PYSEC-2026-1994", "PYSEC-2026-1996",
}
report = json.loads(open(sys.argv[1], encoding="utf-8").read())
findings = [v for dependency in report["dependencies"] for v in dependency["vulns"]]
unknown = [v for v in findings if v["id"] not in allowed]
if unknown:
    print("Unreviewed dependency advisories remain:")
    for finding in unknown:
        print(f"- {finding['id']}: {finding['description'].splitlines()[0]}")
    raise SystemExit(1)
print(f"Dependency audit reviewed {len(findings)} exact-ID advisories; no unreviewed finding remains.")
print("Applicability owner: Release Engineering; next required review: 2026-09-01 or before deployment.")
print("Advisories in the explicit applicability/upstream-availability review list:")
for finding in findings:
    print(f"- {finding['id']}")
PY
  elif [[ ! -s "$audit_report" ]]; then
    echo "pip-audit completed without a JSON report." >&2
    exit 1
  else
    echo "Dependency audit found no advisories in runtime dependencies."
  fi
else
  echo "pip-audit is not installed; install the security extra before release scanning." >&2
  exit 2
fi
npm --prefix apps/web audit --audit-level=high
