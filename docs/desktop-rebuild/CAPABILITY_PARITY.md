# Capability preservation ledger

Baseline: 2433fba47c. Every row begins as a gap until verified through the desktop. Retained backend files alone do not prove UI parity.

| ID / capability | Retain or restore | Target access and key acceptance |
|---|---|---|
| P01 Record and provenance | Append-only events, immutable items, typed edges, derived indexes, corrections/tombstones | Records reopen with identical facts and IDs; index deletion/rebuild does not lose facts |
| P02 User knowledge + project records | User-wide learning graph, project/course research records, cross-record context | One workspace switcher; sources/graphs never mix same-ID entities across records |
| P03 Director and task orchestration | Brief, engage, work, priority, first claim wins, triggers, optional jobs | Start goal → actual queued/claimed work → persisted outcome; no fake background activity |
| P04 Adaptive learning | Probe, prerequisite frontier, policy reasons, prepared bundles, teach/check/recall/review, FSRS | One real lesson with delayed/free-answer grading and accurate mastery state |
| P05 Advanced pedagogy | Socratic hints/reveal; intuitive/intermediate/formal depth; tiered practice; Bloom tasks; learn-back/source comparisons; bounded analogies; key terms/categories; role-specific feedback | Contextual “Explain”, “Practice”, “Compare My Summary”, “Terms” actions; exact attempt/version binding; assisted work never becomes unaided |
| P06 Revision and drafts | Raw answers, history, help attribution, preserved previous explanations, unsent drafts | Reload and switch sessions without losing work; late feedback cannot grade a newer answer |
| P07 Lessons and reading | Meaningful section titles, freely navigable prepared stages, TOC, open questions, exact links | Navigation does not mark a step learned; questions live in a side dock |
| P08 Media and voice | Formula speech, Kokoro/adapters, Whisper, prepared narration, replay/speed, SVG, diagrams, Manim, vetted clips, 3D artifacts where historical support exists | Inline placement, captions/provenance, click-to-load remote media, independent text reading |
| P09 Live-board outcome | Sequential visual derivation synchronized with narration, retained position | Prepared visual/animation timeline fulfills teaching outcome without restoring obsolete blackboard/plugin infrastructure; verify against historical behavior |
| P10 Handouts | Lecture, recitation, chapter, literature and findings; native reading, Markdown, LaTeX/PDF, separate solutions | Study order preserved; annotated PDFs and user notes never overwritten |
| P11 Literature and access | Scout, paper catalog, dedupe, evidence atoms, source/regime/observable checks, access handoffs | Paper/source detail with exact locators, verification status, honest access failure; institution sign-in stays in browser/provider, no stored credentials |
| P12 Research cycle | Frame → scout/verify → learn evidence → plan → human approval → build/run → audit → defend → human decision → persist | Native stage view and forms; all gates remain meaningful |
| P13 Scientific audit | Number/citation/source/result/integrity checks, assumptions, statistics/math/physics and adversarial lenses, fresh-context review | Exact evidence trail; author cannot pass off its own output as independent audit |
| P14 Ownership | Defence items, code walkthroughs, method literacy, commitments, proposals, waivers | Explain method/result/code from relevant artifact; waiver explicitly human |
| P15 Computation | Manifests, seeds, environments, input/output hashes, scale ladder, optional Geant4/ROOT/ML/QML tool packs | Existing tool discovery/guides reachable from Research → Tools; runs retain provenance |
| P16 Notebook coverage | Coverage vs mere mention, module/test/map evidence, first-seen/closed gaps | Codebase → Understanding Coverage; derived ledger, no inference that a test file means tests passed |
| P17 Notebook trace/mutation | Approved notebooks, scratch execution, stored vs fresh output, bounded mutations, dependency groups | Run details and approval controls; no execution on attachment; original repo unchanged |
| P18 Graphs and plans | Knowledge, research, evidence chain, progress, gaps, roadmap, goals, deadlines | Graph lens switch, accessible list, source navigation, prerequisites and review dates |
| P19 Vault | Ownership hash, generated regions, My Notes, flow-back, Inbox, MOCs/Bases/canvases, daily reviews, conflicts | Sources → Vault; preview/sync/status/conflict resolution, Open in Obsidian |
| P20 Import/export/migration | Legacy sessions/state/notes/papers/tasks/resources/visuals/handouts/evidence; migrate_check; static export | Read-only migration inventory first; every file accounted for with proof or explicit explanation |
| P21 Handwritten notes | Faithful notes-to-LaTeX contract, uncertain marks, source preservation | Attach scan/PDF → transcription draft → review; optional extraction engine can be unavailable honestly |
| P22 External agents | Existing CLI, MCP, install/config adapters, provider-neutral skill/role instructions | Desktop work and external Codex/Claude sessions observe the same record and task status |
| P23 Local operation | Prepared reading/reviews, graph/search, records and sources independent of cloud | App opens and remains useful without provider access or Obsidian |



## Evidence and status

The implementation uses the canonical Python operations and native workspace views. Tests use disposable records, repositories and deterministic providers. Real model accounts, scientific hardware and personal vaults were not used. Those deployment checks remain distinct from implemented parity. INVENTORY.json records the current tool, importer, gate, engine, skill and role tables.

| ID | Final implementation and access | Status | Verification and limits |
|---|---|---|---|
| P01 | Existing append-only store, graph, items and rebuildable indexes; immutable source/output blobs | preserved | Store/index/migration suites; atomic one-shot claims tested across stale Record instances. |
| P02 | Workspace switcher, user/project context, explicit external codebase identity and relocation | preserved | Record-aware browser navigation and source identity/isolation regressions. |
| P03 | Home modes, AgentAction, governed director/task tools, actual tool receipts and Research Operations | equivalent replacement | Director routing E2E and agent operation fixture persist outcomes in the claimed record. No inferred effects from prose. |
| P04 | Learn probe/frontier/policy/answer/grade/FSRS and prepared bundles | preserved | Existing learning/policy suites and complete lesson browser scenarios retained. |
| P05 | Version-bound pedagogy dock for hints/depth/tier/Bloom/terms/summary comparison | restored | Pedagogy contracts bind assistance to exact attempts before exposure; raw summaries never infer mastery. |
| P06 | Immutable answer and message history; isolated drafts and acknowledgement guards | preserved | Frontend draft/dictation/model contracts and browser history/navigation. |
| P07 | PreparedReading stages/TOC, contextual questions and retained reading position | equivalent replacement | Lesson-material retrieval/help attribution; stage navigation makes no learning event. |
| P08 | Kokoro/Whisper adapters, narration speed/position, SVG/Mermaid, Excalidraw, animation/poster/keyframes, verified clips | equivalent replacement | Rendering/browser and media host/interval tests; optional installed voice/Manim/3D-rendering engines remain required for generation. Historical 3D scenes produce rendered video/keyframes. |
| P09 | MediaSequence binds sequential narration steps to visuals and saves replay position/speed | equivalent replacement | Prepared segment contracts and native playback controls; obsolete blackboard runtime not restored. |
| P10 | Native handout reader, separate solutions/study order, Markdown/Print/PDF and existing TeX engine | preserved | Handout/PDF suites and workspace reader/browser exports. Optional TeX installation remains explicit. |
| P11 | Public Crossref/Europe PMC metadata, retained sources and exact citations; catalog/access/reliability tools | equivalent replacement | Retrieval fixture records request/time/response hash and unverified candidates; HTTPS links open external browser. Metadata never claims full-text verification. |
| P12 | Native Research stages, approved exact plan, separate execution permission, saved runs/artifacts, audit/defence/decision forms | equivalent replacement | Actual browser computation and domain research gates; independent scientific audit remains a separate reviewer act. |
| P13 | Integrity/result/number/citation/kill-argument engines and independent reviewer roles | preserved | Existing scientific review suites; authoring runtime excludes verdict and human decisions. |
| P14 | Native ownership/decision controls and contextual defence/code/commitment tools | preserved | Existing ownership/defence suites; explicit human waiver remains enforced. |
| P15 | Research code staging, immutable inputs, bounded worker, actual output hashes/manifest; optional scientific guides/engines | equivalent replacement | Real fixture computes 42 through plan approval and separate permission, downloads retained artifact. Geant4/ROOT/ML/QML are optional installed tool packs, not bundled or hardware-certified. |
| P16 | Historical notebook coverage engine in Codebase Understanding Coverage | restored | Ported coverage tests distinguish imports, mentions and test-file existence; preserve first-seen/closed gaps. |
| P17 | Historical trace/mutation engine, exact notebook revision, named permission and scratch committed clone | restored | Ported trace tests and stale-commit guard. Live uv/kernel execution is optional; scratch is data isolation, not an OS sandbox. |
| P18 | Four graph lenses, worker layout, bounded neighborhood, accessible list and roadmap | equivalent replacement | Workspace/desktop browser and sparse/dense benchmark; cancellation and late layout results tested. |
| P19 | Explicit vault connection/destination, preview/sync/conflict resolution and Open in Obsidian | equivalent replacement | Canonical ownership/My Notes/conflict suites retained; no personal vault or actual Obsidian launch performed. |
| P20 | Canonical importer/migration inventory/check/export forms in Advanced Operations | preserved | Existing accounting suites retained; no automatic migration on startup or connection. |
| P21 | Image/PDF attachment, locally rendered pages, configured vision, immutable transcription drafts and exact human review | equivalent replacement | Synthetic media consent/scope tests, local PDF rendering, transcription revision/review tests; no personal scans sent to a provider. |
| P22 | CLI/MCP/install protocols and native Codex/Claude plus Ollama/compatible transports | preserved | Native protocol fixtures, strict scoped tools and committed effects; real login, entitlements and model quality are deployment-specific and untested. |
| P23 | Local records, prepared reading/reviews, graph and source indexing/search independent of provider/vault | preserved | Native empty-start smoke, browser source journeys and explicit 10k-source benchmark. |

No historical capability is declared nonexistent to excuse its removal. The UI exposes existing specialized operations through contextual forms and a searchable advanced tool surface; normal reading, source, conversation, computation and approval paths have dedicated views. Optional engine availability is reported at the relevant operation. ACCEPTANCE.md lists the actual completed checks and limitations.
