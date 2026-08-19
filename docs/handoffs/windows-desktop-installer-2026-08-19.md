# Windows desktop installer handoff — 2026-08-19

## Outcome

Beyond Fire Radar now has a Windows x64 desktop distribution path. The NSIS installer contains the existing Next.js dashboard and a frozen FastAPI backend. The desktop shell starts at Windows sign-in, continues source polling while the dashboard window is hidden, and exposes Open, Check for updates, and Quit controls from the system tray.

## Data and update safety

- The application program files live in the per-user installation directory.
- The alert database, raw snapshots, logs, and backups live under the current user's Windows AppData directory and are not packaged into or removed with application updates.
- The NSIS configuration explicitly keeps AppData during uninstall.
- Restart to update creates a consistent SQLite backup before stopping the background services or invoking the updater. A backup failure stops the update rather than proceeding without the safety copy.
- Only the newest pre-update database backup is retained because a populated local property database can be large. Existing raw snapshots are not copied for each update, but they remain outside the replaceable installation directory.
- The bundled backend runs every included Alembic migration before starting the API. Migrations remain additive and versioned; the pre-update backup provides the recovery boundary for a failed future migration.

## Release workflow

- `.github/workflows/windows-installer.yml` runs on a Windows GitHub runner for manual builds and version tags.
- The workflow installs locked web/desktop dependencies, runs the repository verification contract, builds the Next.js standalone runtime and PyInstaller backend, starts the frozen backend against a fresh SQLite database, probes readiness, then builds and hashes the NSIS installer.
- A manual run uploads the installer, `latest.yml`, and blockmap as a workflow artifact. A `v*` tag publishes those same files to a GitHub Release for the in-app updater.
- The installed Settings view supports Check for updates, Download update, and Restart and update. Downloads use the checksum recorded in the generated update metadata.

## Verification evidence

- `./scripts/verify.sh` — passed: 92 Python tests, Ruff formatting/lint, mypy, web lint/type validation/production build, and 2 desktop runtime tests.
- Isolated `./.venv/bin/python scripts/dev.py migrate` — passed through `0027_property_master_relationship_index`.
- Isolated `API_BASE_URL=http://127.0.0.1:28742 ./.venv/bin/python scripts/dev.py api-smoke` — passed.
- `npm --prefix desktop run prepare:web` — passed; the standalone route manifest targets the packaged backend at `127.0.0.1:28741`.
- macOS PyInstaller structural build — passed. The frozen backend migrated a fresh SQLite database through `0027`, returned 200 from `/readyz`, created a live consistent backup, and the backup returned `ok` from SQLite `integrity_check`.
- Standalone runtime smoke — passed: dashboard `/` returned 200 and `/api-backend/readyz` proxied to the packaged backend with 200.
- `git diff --check` — passed.

## External gates

- This macOS host cannot execute the Windows installer, validate Windows sign-in startup, exercise the system tray on Windows, or run a true in-place Windows update. The GitHub Windows workflow covers the build and frozen-backend smoke, but a client-like Windows install/reboot/update/uninstall exercise remains required.
- The installer is unsigned unless the repository receives `WIN_CSC_LINK` and `WIN_CSC_KEY_PASSWORD` secrets. An unsigned first release can trigger Windows SmartScreen and does not support a publisher-trust claim.
- Unauthenticated GitHub Release updates require the repository/releases to be public. A private source repository needs a separate public update channel or client-side GitHub authentication. No GitHub token is embedded in the installer.
