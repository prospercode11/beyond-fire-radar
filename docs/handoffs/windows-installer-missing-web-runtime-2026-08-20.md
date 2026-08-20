# Windows installer repair — missing packaged web runtime — 2026-08-20

## Reported failure

A client installed `Beyond-Fire-Radar-Setup-0.1.0.exe` on Windows 11 and the app refused to start:

```
Beyond Fire Radar could not start
Web server is missing: C:\Users\<user>\AppData\Local\Programs\Beyond Fire Radar\resources\web\server.js
See C:\Users\<user>\AppData\Roaming\beyond-fire-radar-desktop\logs\desktop.log for details.
```

The installer really did ship without `resources/web`. The backend was packaged correctly, which is why startup failed at the dashboard step rather than the backend step.

## Root cause

Four defects lined up, all in the release path rather than in the application:

1. `desktop/scripts/prepare-web.cjs` ran the web build with `spawnSync("npm.cmd", ["run", "build"])`. Node 20.12 and later refuse to spawn a `.cmd` file without `shell: true` and fail with `EINVAL`. On macOS `npm` is an ordinary executable, so the script worked on the development host and could never have worked on Windows.
2. The `Build Windows backend and web runtime` workflow step ran `prepare:web` and `build:backend` as two lines of one PowerShell step. PowerShell does not stop at the first failing command, and the step's status came from the last command, so the failed web build was reported as success. `desktop/.build/web` was never created.
3. `electron-builder` treats a missing `extraResources` source as a warning, not an error. The build log contains `• file source doesn't exist from=...desktop\.build\web` and packaging continued.
4. `Verify installer artifacts` only checked that the installer and `latest.yml` existed, so nothing inspected what was inside the installer.

Evidence: GitHub Actions run `32312412030` (the run whose artifact became the `v0.1.0` release) contains the `file source doesn't exist` warning, and its build step is 43 seconds long — PyInstaller only, with no Next.js build in it.

## Second defect, found by the new gate

The first CI run of this fix failed at the new `afterPack` check with `Dashboard dependencies: ...\resources\web\node_modules\next` missing, and the failure reproduced locally with `electron-builder --linux dir`: 77 of 1,979 prepared files were packaged.

`app-builder-lib/out/util/filter.js` rejects a matcher's own root `node_modules` before any pattern is evaluated:

```js
// filter the root node_modules, but not a subnode_modules
if (relative === "node_modules") {
  return false;
}
```

That filter is applied to every matcher, `extraResources` included, and no `filter` pattern can override it. A single `{ from: ".build/web", to: "web" }` mapping can therefore never carry the dashboard's dependencies. The defect was present in the original configuration as well; it was hidden because the whole directory was already absent.

`node_modules` is now mapped as its own entry, `{ from: ".build/web/node_modules", to: "web/node_modules" }`, where the excluded name is never the matcher's root, and the web entry excludes `node_modules` so the two do not copy the same files. `desktop/tests/packaging.test.cjs` pins that layout, since the failure mode is silent.

## Changes

- `desktop/scripts/prepare-web.cjs` now starts the Next.js CLI through `process.execPath` with the CLI path resolved out of `apps/web/node_modules`, so no shell and no `npm.cmd` is involved on any platform. Spawn errors, signals, and non-zero exits each fail with a specific message.
- The same script now tolerates either standalone layout. Next.js emits `server.js` at the standalone root when it traces `apps/web`, and under `apps/web/` when it infers a workspace root above it; the output is flattened so `server.js` is always at the root of `resources/web`. It then verifies `server.js`, `.next/static` (non-empty), `.next/required-server-files.json`, and `node_modules/next` before reporting success.
- `desktop/scripts/verify-package.cjs` checks a packaged application directory for the dashboard server, browser assets, dashboard dependencies, and the backend executable, and with `--boot` starts the packaged `server.js` and requires an HTTP 200 from `/`.
- `desktop/scripts/after-pack.cjs` runs the structural half of that check as an electron-builder `afterPack` hook, so an incomplete package now fails the build instead of producing an installer.
- `desktop/main.cjs` checks all four runtime resources before launching anything and reports every missing piece in one actionable dialog. It also stops child processes with `taskkill /T /F` on Windows, where a plain kill leaves the backend holding the SQLite file, no longer starts a runtime when a second instance loses the single-instance lock, and restarts the dashboard process (bounded at five attempts) if it exits while the app runs.
- `.github/workflows/windows-installer.yml` builds the web runtime and the backend in separate fail-fast steps, asserts the prepared tree, verifies the packaged tree by booting it, and then performs a silent install of the built installer and verifies and boots the installed tree.
- `desktop/package.json` is at `0.1.1`, since `0.1.0` is a published broken artifact and the updater needs a higher version.

## Verification evidence

- `PYTHON_BIN=python3 ./scripts/verify.sh` — passed: Ruff formatting/lint, mypy, 92 Python tests, web lint, Next.js production build, and 9 desktop tests (2 pre-existing, 7 new).
- `python3 scripts/dev.py migrate` — passed through `0027_property_master_relationship_index`.
- `API_BASE_URL=http://127.0.0.1:28900 python3 scripts/dev.py api-smoke` — passed.
- `npm --prefix desktop run prepare:web` — passed on Linux: 1,979 files prepared, standalone entry `.`.
- `node desktop/scripts/verify-package.cjs --dir <tree> --boot` against a packaged-shaped copy of that output — passed: the packaged `server.js` served HTTP 200.
- The same check against a tree with `resources/web` deleted — failed with exit code 1 and named all three missing dashboard paths. The `afterPack` hook rejected the identical tree. This is the exact condition that shipped in `v0.1.0`.
- `npx electron-builder --linux dir` against the repaired configuration — passed: `afterPack` verified the packaged tree, 1,978 of 1,979 prepared files were packaged (only `public/.gitkeep`, a placeholder, is dropped), and the packaged dashboard served HTTP 200.
- New desktop tests cover both standalone layouts, the flattening result, rejection of a runtime missing `server.js`, rejection of empty browser assets, the packaged Windows/macOS resource layout, and the incomplete-installation report.

## Windows verification evidence

GitHub Actions run [`32408935527`](https://github.com/prospercode11/beyond-fire-radar/actions/runs/32408935527) on `windows-latest`, commit `3bd15fa`:

- `Run repository verification` — passed.
- `Build Windows web runtime` — passed in 20 seconds. The equivalent step in the `v0.1.0` build was a 2-second silent failure.
- `Verify prepared web runtime` — passed.
- `Build Windows backend` and the packaged-backend migration/readiness smoke — passed.
- `Build NSIS installer` — passed, including `after-pack: verified runtime resources in ...\release\win-unpacked`, and produced `Beyond-Fire-Radar-Setup-0.1.1.exe` with SHA-256 `26bff3ea18c8591b8f8c343c971323dd3a2f7f7499f529d39d00163c13fae22d`.
- `Verify packaged runtime resources` — passed: `verify-package: packaged dashboard served http://127.0.0.1:51682/`.
- `Verify the installer installs a runnable application` — passed: a silent install into `D:\a\_temp\bfr-install` produced the application executable, and `verify-package: packaged dashboard served http://127.0.0.1:51699/` confirmed the installed dashboard serves HTTP 200. This is the exact condition that failed on the client machine.
- `Upload workflow artifact` — failed on this run only, because the artifact name embedded a branch ref containing a slash. That is a pre-existing workflow defect that never surfaced on `main` or on a tag; the artifact name is now flattened before upload. It is packaging-independent and did not affect the installer.

## External gates

- The `npm.cmd` spawn failure is Windows-only and cannot be reproduced on this Linux session; it is fixed by removing the `npm` spawn entirely. The Windows workflow is the verification, and its new steps fail the build if the dashboard is absent for any other reason.
- A Windows client install, sign-in startup, tray, in-place update, and uninstall pass is still required and still outside this environment.
- `Beyond-Fire-Radar-Setup-0.1.0.exe` on the `v0.1.0` release remains a broken download until it is removed or replaced. Clients on `0.1.0` cannot self-update, because the app exits before the updater is reachable; they need the new installer directly.
- The installer remains unsigned unless `WIN_CSC_LINK` and `WIN_CSC_KEY_PASSWORD` are configured.
