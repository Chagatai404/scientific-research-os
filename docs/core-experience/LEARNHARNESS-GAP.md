# Features adopted from a comparable learning harness (2026-11-10)

Compared against the public LearnHarness repository (commit da08cb5). That project is AGPL-3.0;
Research OS is MIT. **No code, prompts or text were copied.** Only feature ideas are re-implemented
here, from behaviour descriptions, in this repository's own architecture. Nothing below changes the
research core: evidence, claims, audits and human decisions keep their existing contracts.

| Adopted feature | Why it helps here | Slice |
|---|---|---|
| Tool-argument repair before validation (JSON-in-string arrays/objects, quoted scalars) with a repeated-rejection loop breaker; every repair is logged; never applied to verdict, grade, approval or decision arguments | Local and direct-API models often send mechanically malformed arguments and loop on rejections | L1 |
| Narration guard: a model that writes learner-facing prose outside the reply path is redirected once | Local models narrate instead of answering | L1 |
| Turn liveness: one active turn per conversation, heartbeat, stale-turn sweep to `interrupted`, stream reattach after reload/window close; queue a steering message into a running turn; retry a failed reply without resending the failed tail | Long tutoring/research turns survive closing the app and are controllable | L2 |
| Usage and cost meter per conversation and workspace, context-window gauge, explicit "unknown" when a provider reports no usage | People on pay-per-token API profiles need budget visibility | L3 |
| Conversation compaction for model context: older turns summarised behind a visible divider; the record keeps every original turn; a summary is never evidence | Long sessions overflow local-model context windows | L4 |
| Display-only math repair (model escaping defects such as stray `\n`/`\t` inside TeX), in-conversation find (Ctrl+F) and a keyboard shortcut cheat sheet (`?`) | Math-heavy lessons; navigation in long sessions | L5 |
| General web search and page reading, where every page becomes a captured source with provenance and local-only material never enters a web query | Scholarly APIs miss general web sources | merged into S6 |
| Extraction coverage: which taught material has not yet reached the knowledge graph (agent-facing, not a person task) | Keeps the living graph complete | merged into S8b |
| Release verification job: the release must contain every installer and the update feed | Protects the desktop update path | merged into S10 |

Already present (no work): probe/plan/teach/practice loop, knowledge graph with provenance, notes import,
Claude Code/Codex providers and custom endpoints (S4), dictation, PDF reading, background research agents,
activity board, Markdown export. Rejected: editable system prompts (could weaken audit prompts), parked
dismissals, prompt-cache preference, learner image markup (low value now).
