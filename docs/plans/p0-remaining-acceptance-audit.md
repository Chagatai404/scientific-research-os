# Remaining P0 acceptance audit — 19 October 2026

Scope: the complete supplied adaptive-learning brief, reconciled with the current
implementation record and repository at `b54e408`, plus the completed parallel P0 slices and final context-writer checks. This is an acceptance map, not a release declaration. VERSION remains 0.9.7.

## Mandatory core versus later work

| Requirement | Current evidence / boundary |
| --- | --- |
| Canonical bounded knowledge inspection, unknown/stale/fragile/current distinctions | Implemented in context_kernel/tutor_plan; cached advice projection and refresh tested by adaptive-context/advice suites. Genuine missing essential roots block rather than invent knowledge. |
| Free stages and retained answers/lecture state | Implemented in stages/session writers, existing desktop/narrow browser regressions. Host-backed unsent reload recovery is implemented and independently tested (a2685fe). |
| Immediate handout before Quiz and PDF | Native bounded readable content/publisher implemented; complete revisioned Markdown library copy, sources, math, solutions and focus. PDF is optional. Structural source records are not verification of source truth. |
| Text-only diagnostic, teaching, typed Check | Implemented with board-independent text presentation and real checked local numerical/choice branches. Free reasoning remains pending substantive review. |
| Review-driven adaptation | Reviewed latest attempt affects unstarted prepared repair; started path remains frozen; unavailable repairs requested honestly. No autonomous generated-content repair or systemic P1 behavior claimed. |
| Objective/time/language/depth route preferences | Implemented in ea581ed: trusted explicit-choice persistence, startup/resume policy, bounded display and tutor-mediated change request; offline desktop/phone checks pass. |
| Staged Check to canonical evidence handoff | Previously missing: ordinary tutor_gate proposal accepted only ordinary question/response history. New plan_evidence module projects an explicitly mapped written Check through the existing evidence gate without copying responses or writing a ledger. See contract below. |
| Optional workers absent | New integrated browser removes board/voice globals, leaves PDF unbuilt, strips video segments, blocks every HTTP request, and has no audio/tablet/GPU/LaTeX service. Existing browser suites cover optional video transitions and board failures. |
| Existing scientific integrity and retention | Real writer tests compare original ledger bytes and raw events. Proposal explicitly says retention not assessed. Human acceptance/promotion stays a separate workflow. |
| Current context at changed teaching boundaries | Generic prose/questions/boards/resources/declarations and new tutor answers check bound context under the existing lock; 132 final integration tests and the real-writer browser flow pass. Historical/waived compatibility and raw submissions remain available. |
| Actual desktop Obsidian installation | Pending explicit installation approval and real host verification. Offline sandbox Chromium cannot prove plugin lifecycle or actual vault behavior. |

The brief places systematic Socratic hints, explanation levels, tiered practice,
summary comparison, term categorization, Bloom, analogies and ALTER behaviors in
P1. It places tablet integration in P2 and further performance/accessibility,
realistic evaluation and portability in P3. They remain implementation work;
calling the P0 text core functional does not complete those requirements.

## Integrated offline fixture

`tests/support_p0_text_flow.py` creates a disposable vault with canonical
expectation and variance concepts. Expectation has current conceptual evidence;
variance starts unknown. It binds actual context, prepares the existing variance
lesson, publishes a native handout before any answer and leaves PDF planned.
It removes video dependency and adds a genuinely different finite-distribution
written Check. The fixture source is conspicuously synthetic, with no fabricated
claim of source vetting.

`tests/test_p0_text_flow.py` exercises real startup, context recommendation,
append/lock/review writers, partial reasoning -> prepared repair, frozen lecture,
independent written Check, and read-only mapped evidence proposal. Exact Fraction
arithmetic independently checks mean 1, variance 9 and shift invariance. Scripted
review provenance remains explicit; tests do not evaluate a model's grading.

`tests/html-p0-text-flow-browser.cjs` actually clicks/enters the full keyboard flow
in headless dark desktop Chromium with reduced-motion preference. Its sandbox
host echoes local events, then batches those exact event IDs through the real
Python writers and scripted criterion reviews at diagnostic/Check boundaries.
The final Check proposal names that same original event ID. Assertions preserve
all three diagnostic answers and exact canonical ledger bytes. No HTTP listener,
external browser window, network service or live vault is used.

## Staged evidence proposal contract

`scripts/plan_evidence.py` is provider/host-neutral and read-only. Its explicit
reviewer mapping names: exact prepared-question SHA-256; canonical capability;
scope/dimension/method; TESTS/ASSUMES/INTRODUCES; independent-example assertion
when transfer; assistance; mapping-reviewer identity; exact response event ID and
answer digest; and an explicit reviewer attestation that this question was actually
shown for that attempt. It checks canonical
identity and existing schema/scope/method/assumption rules, then delegates the
proposal assessment to `tutor_gate.evidence_proposal`. Only written Check items
are supported. Local recognition/numeric results do not become conceptual credit.

The latest actual Check answer must have a substantive review, full applicable
criteria, and actual answer-reviewer provenance. Old reviews never approve a newer
attempt. Unknown/mismatched mappings fail closed. The original answer is neither
duplicated nor rewritten; an internal transient view supplies the existing gate.
An earlier native appendix reveal conservatively forces open-notes assistance.
Recorded solution exposure also forces open notes; a prior hint or explanation
request conservatively forces hinted assistance. Explicit declared hints/open-notes prevent independent demonstration. The module
also accounts for late-arriving help with timestamps at/before the attempt and treats unknown timing conservatively. Valid help strictly after the attempt is not retroactive. It cannot detect undisclosed off-screen help and does not claim it can.

`html_sessions.answered_plan_changes` now protects answered prompts, criteria,
option keys, solutions and all other assessment semantics through both ordinary
plan update and review-with-revision writers. Explicit `allow_reroute` can change
only pacing routes; it cannot rewrite the question a historical answer responded
to. Use a new question ID for changed semantics. One old test that authorized
correct-option rewrites was deliberately tightened; a new route-only override
regression preserves the intended explicit-pacing capability.

Historical events do not store question hashes. A hash of today's question alone
cannot prove what an old UI showed; the explicit reviewer attestation remains
necessary for historical sessions. The adapter reports this limitation and never
fabricates historical provenance. New writer guards prevent future semantic
rewrites through those writers; they do not repair old records retroactively.

The CLI prints a proposal for human acceptance and never writes canonical
learning state, grants retention, changes retention targets, promotes permanent
notes or accepts research results. No generic canonical writer is invented.

Example invocation (all paths must point to the intended authorized/disposable
vault; this audit does not authorize live-vault use):

```powershell
python scripts/plan_evidence.py --root <vault> --session <session.md> `
  --question novel --mapping <reviewed-mapping.json> --learning-root <records>
```

## Verification record and remaining acceptance

Commands: `python -m unittest discover -s tests -p test_p0_text_flow.py -v` and
`node tests/html-p0-text-flow-browser.cjs` with existing local Playwright/Chrome.
Final targeted run: 12 new Python tests passed in 42.7 seconds, no skips or errors.
The existing session-plan suite passed 58 tests in 35.3 seconds, no skips or errors.
The integrated browser passed with zero external requests; final simulated click-to-
readable handout 1098 ms, Quiz navigation plus selection/check 1857 ms. These include
Playwright overhead and do not isolate computation time, production performance,
content generation, real-device latency or educational effectiveness.
The dark desktop Check screenshot was visually inspected. The existing browser
regressions and parent integration run own narrow layouts; this new end-to-end
fixture itself tests desktop only. Earlier transient startup failure during
concurrent bundle work cleared in the final run; it is not hidden as a green run.

Parallel preference/draft changes are committed and their dedicated gates pass. Final aggregate regression results are recorded in the main implementation plan, including 132 final Python tests and a fresh integrated browser pass. P0 repository implementation is complete within this offline scope. Repository implementation does not establish live Obsidian acceptance or source truth; the manual gates below remain explicit.

Manual gates remain:

- Approve a backed-up runtime/helper installation in the local Obsidian vault;
  open old and new sessions, study offline, switch stages, reload/reconnect, submit
  typed answers, receive a real review, and inspect exact retained raw work.
- Human reviewer validates a genuine course source and criterion-bound Check,
  reviews the proposal, and chooses any authorized canonical record update. A
  generated fixture must never be presented as demonstrated learner knowledge.
- Real PDF compilation is verified: all 28 handout tests passed with access to
  the existing MiKTeX installation, including the two previously skipped real
  compile tests (`adaptive-p0-real-pdf-gates.json`). Audio still needs microphone/
  device consent; neither enhancement is required for P0 text acceptance.
- iPad/Android stylus, pairing, LAN/TLS/firewall and live-ink latency remain P2
  gates. No physical-tablet or network-security validation occurred here.
- Representative full STAT303 bias/MSE and research-linked box-counting lessons,
  expanded scientific fixtures and actual pre/post/transfer/delayed learner study
  remain later evaluation work. The small variance fixture is narrower than those
  required final evaluations and cannot substitute for them.
