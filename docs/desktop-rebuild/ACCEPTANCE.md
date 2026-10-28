# Desktop acceptance evidence

Verified 2026-10-28T12:58:17+03:00 (Europe/Istanbul). Windows 11 AMD64, Python 3.14.4, Electron 43.8.4. Branch `agent/codex/desktop-rebuild`, based exactly on `2433fba47c753bc3f2c4eac6045ba91b14b9f534`. No push, merge or public release.

## Deliverable and launch

Install [Research OS 1.3.0](../../desktop/dist/Research-OS-Setup-1.3.0-x64.exe). It includes Electron and the frozen backend, creates shortcuts, and preserves records on uninstall. The complete unpacked application is [Research OS.exe](../../desktop/dist/win-unpacked/Research%20OS.exe). Keep its adjacent resources. The installer is unsigned; no signing identity was supplied. ARTIFACT.json records final SHA-256/SHA-512 and byte sizes. The earlier preview ZIP is superseded.

Installed copies check the public GitHub stable-release feed and download newer versions automatically. Settings shows progress and permits restart after active owned work finishes. Publication requires an explicit matching `desktop-v<version>` tag; no release was published in this session. Unpacked/development copies use manual replacement. Backend version 1.2.1 is retained for compatibility; desktop package version is 1.3.0.

## Complete verification

`python desktop/verify.py` passed all nine checks on the final functional tree. Python: **822 tests, 8 optional/platform skips**, 569.003 s. Frontend: **21 tests**. Electron lifecycle/updater unit tests: **6 tests**. Timing budgets and browser assertions were retained. Cold vault reads were profiled and fixed with bounded prefetch, with new ordered-write/warm-no-read regression coverage.

| Check | Result | Duration |
|---|---|---|
| python | PASS | 571.594 s |
| frontend-tests | PASS | 31.526 s |
| typecheck | PASS | 7.965 s |
| frontend-build | PASS | 89.777 s |
| legacy-browser | PASS | 31.774 s |
| workspace-browser | PASS | 30.951 s |
| desktop-browser | PASS | 17.465 s |
| workspace-benchmark | PASS | 308.34 s |
| desktop-lifecycle | PASS | 5.977 s |

Raw logs and machine-readable results: [evidence/gate-results.json](evidence/gate-results.json). The legacy portal remains a compatibility test; desktop workflows use the native workspace. Browser evidence covers source privacy/Unicode/revisions, real bounded computation and retained output, learning/questions/assistance, draft/dictation races, record isolation/SSE, graph lenses/navigation, sanitized math/GFM/diagrams, dark/light, seven widths (320–1920), 1280×720 and 200% zoom. Screenshots are under screenshots/; the computation artifact view and native launch were visually inspected.

## Packaged application and installer

- Native packaged GUI: exit 0, protocol `ros.desktop.v1`, no horizontal overflow. [packaged-smoke.json](packaged-smoke.json) points to the actual screenshot. The earlier `0x80000003` reproduced only in the restricted launch environment; native launch outside it passes.
- Frozen backend with Python removed from PATH: **148 tools**, local PDF-to-PNG rendering and actual bundled-Python computation pass. [frozen-smoke.json](frozen-smoke.json).
- Actual NSIS **install → installed app launch → uninstall** passes in a guarded workspace destination. The installed executable is removed and an independent record sentinel is preserved. Existing Research OS installs are protected by a registry preflight. [installer-smoke.json](installer-smoke.json).
- Real electron-updater downloaded the installer to 100% and reached ready against a loopback future-release fixture. A corrupt SHA-512 was rejected. No test installed an update. [positive](updater-smoke.json), [corrupt](updater-corrupt-smoke.json).

## Performance measurements

Native release automation: three launches, p50 **3942 ms**, p95 **5153 ms**; 50 navigation cycles, probe p50 **136 ms**, p95 **161 ms**. Navigation probes include a 120 ms settling interval and do not represent pure render time. These measurements do not meet the proposed 2 s warm-launch target; the observed cold maximum is slightly above 5 s. The navigation probe also exceeds 150 ms while including its fixed delay. They remain performance optimization limits, not hidden passes. Process/window/SSE counts and Electron/owned-backend memory are captured in [native-performance.json](native-performance.json). Small samples on one host do not establish a general latency or memory-leak bound; inspect warm-up and retained caches separately from model processes. The uncollected working-set run is preserved in native-performance-before-gc.json. Forced-GC observations retain the same DOM/window/stream counts and less than 1 MiB JavaScript-heap growth; allocator working set still warms over the run. A 1k-visible-node FPS stress test and provider first-token latency are not certified.

Explicit 10,000-file synthetic Markdown source index: listing **33.601 s**, indexing **268.567 s**; indexed search cold **10.4 ms**, warm p50 **6.69 ms**, p95 **8.31 ms**. [source-performance.json](source-performance.json). This fixture excludes PDF OCR and embeddings. Sparse/dense graph timings and bounded payloads are in the workspace benchmark log.

Bundled workspace assets: initial index JS+CSS **887,521 bytes**, total workspace **7,225,981 bytes**, uncompressed including optional chunks/fonts/notices. Vite's >500 kB chunk warning remains visible; no budget or warning was disabled.

## Scope and limits

All tests use `ROS_NO_VAULT=1`, isolated records and synthetic content. No personal vault sync/import, private media export, paid inference, model download or credential extraction occurred. Native Codex/Claude protocols and governed tool effects use deterministic fixtures; real logins, entitlements, rate limits, model scientific quality, GPU voice/animation, live uv/kernel and personal Obsidian launch are unverified deployment checks. Optional engines remain explicit dependencies. Windows x64 is the packaged acceptance target; macOS/Linux artifacts are not certified.

Cloud image/PDF transport requires individual human permission for the exact retained revision and configured destination, expires in ten minutes, and is consumed once. Destination changes are rechecked before dispatch. Local Only media is always blocked. PDF rendering is local and records its first-four-page scope. Transcription review preserves the original and prior drafts. Scientific plan approval, claim decisions, independent audits and waivers retain their original authority boundaries. Scratch computation uses local OS permissions and is not an OS sandbox.
