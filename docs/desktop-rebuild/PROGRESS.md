# Delivery complete

Branch agent/codex/desktop-rebuild, baseline 2433fba47c753bc3f2c4eac6045ba91b14b9f534. No push, merge or public release.

- Full nine-check gate passes: Python 822 tests (8 optional/platform skips), frontend 21, typecheck/build, all three browser suites, graph benchmark, and six desktop lifecycle/updater tests.
- Final frozen backend works without system Python: 148 tools, local PDF rendering and bundled Python computation.
- Final NSIS installer passes isolated install, installed app launch and uninstall; record sentinel preserved. Windows icon/version metadata identify Research OS 1.3.0.
- Real updater positive download reaches ready at 100%; corrupt SHA-512 is rejected. No update was installed by these tests. Future stable releases use the tagged GitHub release workflow.
- Explicit Electron profiles isolate native/updater fixtures on Windows; APPDATA overrides alone were insufficient.
- Three native launches and 50 navigation cycles measured, including retained heap/DOM/SSE and owned-backend metrics. Proposed launch/probe budgets are not all met; precise limits are in ACCEPTANCE.md.
- 10,000-file lexical index completes; search warm p95 8.31 ms. Source indexing remains an explicit background action.
- The finished app was launched interactively; native window discovery confirmed Home · Research OS.
- Cloud media requires individual one-turn permission bound to revision and destination. Local Only remains blocked. No paid inference, personal vault sync or personal media export occurred.

Authoritative delivery evidence: ACCEPTANCE.md, ARTIFACT.json and evidence/gate-results.json. Installer: desktop/dist/Research-OS-Setup-1.3.0-x64.exe.
