# Multi-agent workflow error report

**Resolved checkpoint, 2026-10-27:** the timezone fix is now independently approved, and the complete gate
passed: 711 Python tests (7 skipped), 7 frontend tests, production build, 19 legacy browser steps and 36 workspace
browser checks. The checkpoint is committed on `agent/codex/portal-rebuild`; see Git history. Remaining slices
are still unfinished. The following records the earlier morning state and must not be read as current failures.

Verified morning state: 2026-10-27, after the 08:00 Europe/Istanbul cutoff.
Branch: `agent/codex/portal-rebuild`; latest commit remains `fe9a367`.
The implementation below is present in the working tree, not committed or promoted.

| Problem | Evidence and impact | Resolution / remaining work |
|---|---|---|
| Human resume reported task not found | Eng task state was scoped to this isolated checkout; the supplied `--project .` depended on the person's terminal directory | Resumed the same task using the absolute checkout path after the user's explicit instruction to handle it automatically |
| Nested eng workers could not read the repository | Task `6fa96b5d988444778e31df08b5ea00fd` logged policy rejection of even `git status` and `Get-Content`; planner/engineer calls produced no application patch | Cancelled the task after two provider invocations. No command policy was weakened. Continued using built-in agents with separate implementation/test/review ownership |
| Agent account usage limits | Discovery agents hit a limit earlier; the reference reviewer later failed with a reset message of 04:33 AM | Graph implementation, browser tests and independent UI review completed before that failure. The final daily-review timezone fix did not receive independent review. No claim of uninterrupted overnight execution or complete roadmap delivery is made |
| Full Python gate failed after local midnight | 710 tests ran: one failure, seven skipped. Daily review omitted a decision because its UTC start boundary did not match the local calendar day | Implemented a half-open local-day UTC query window and a boundary regression. All 34 vault tests then passed. The full Python suite has NOT been rerun after this fix |
| First UI browser passes found geometry and lifecycle regressions | Node-panel overlap, squeezed phone reading column, stale camera reset, mobile navigation focus, late send navigation and late microphone acquisition | Fixed and reviewed. Final workspace Chromium run passed 36 checks at seven widths plus 1280×720 |
| Performance budgets remain unmet | First-party CSS about 40 KB; combined minified application JS about 742 KB | Consolidation and splitting remain required; passing functional checks do not establish payload-budget compliance |

## Verified implementation and tests

- Graph-first charcoal landing, compact bottom composer, typed directed links, stable point layout, scoped camera,
  accessible node list, bounded selection context and modal phone navigation are implemented.
- Model selection, dictation, Kokoro playback and session-specific drafts remain functional in fake-provider/media tests.
- Cross-record backlinks, node-stamp title caching, exact read-only manifest path lookup and selected-record SSE
  are implemented. They do not complete the remaining classroom or research execution phases.
- Renderer/graph unit tests: **7 passed**. Production build passed.
- Workspace browser: **36 checks passed**, 11.046 s. Legacy browser: **19 steps passed**, 15.567 s.
- Focused canonical-reference tests: **20 passed**. Selected-record transport tests: **12 passed**.
- Vault tests after the timezone fix: **34 passed**. Final full-suite rerun and timezone-fix review remain outstanding.

The remaining master-prompt slices are unfinished, particularly the unified classroom, native human-decision
forms, complete legacy/diagram rendering, bounded conversational task execution and final hardening.
Do not merge or mark the entire rebuild complete from this checkpoint.

The overnight continuation automation was deleted after its morning cutoff. No active implementation agents
remained at that inspection. No push, deployment, main-branch merge or live-vault migration was performed.
