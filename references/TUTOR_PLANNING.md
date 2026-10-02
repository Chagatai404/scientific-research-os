# Concept-first tutor decisions

Teach enough general theory for a concept to be independently understandable and
transferable before relying on project context. A project motivates the lesson;
it does not define the concept or establish mastery. This extends the bounded loop
in `LEARNING_PROTOCOL.md` using `references/KNOWLEDGE_MODEL.md`. Research approvals
and resolution remain separate; this learning plan never gates already approved work.

## Resolve a narrow target

Resolve an explicit capability or mapped concepts from the active project/block.
Inspect the knowledge graph, then use the read-only planner when available:

```bash
python scripts/tutor_plan.py --root "<working-record-root>" --block block-9 --focus box-counting --as-of 2026-10-02
python scripts/tutor_plan.py --root "<working-record-root>" --capability box.ecal-application --context block-9
python scripts/tutor_plan.py --root "<working-record-root>" --concept box-counting
```

The helper emits deterministic JSON containing required concepts, subject/domain
memberships, scoped evidence and attempt references, capability closure and one
next action. It writes nothing. Cache the bounded plan for a block and refresh
after actual evidence, target or dependency changes. Do not save its projections
as another authoritative record or rediscover the vault after every answer.
Without the helper follow these same rules directly from canonical records.

Application mappings use explicit domain/subject/concept links, concept applied_in,
block-to-project membership and capability project/block links. A project includes
its blocks. Broad subject/domain memberships deliberately resolve a broad set;
--focus selects an explicitly mapped concept for the narrow task. Titles, filenames
and project wording are not mappings. Without a mapping, identify/propose the
actual concepts before teaching; an empty plan is not completed learning.

Follow prerequisite/builds_on concept edges and explicit capability prerequisites,
including cross-domain foundations. Related/contrasts_with connections are optional,
not automatic lessons. Do not teach a whole subject or chapter for one prerequisite.
Missing/invalid references and cycles never establish known foundations. The helper
also rejects cycles created by combining concept and capability prerequisite edges.

## Select evidence without merging capabilities

Use an explicit target/required conceptual capability profile when present,
otherwise the sole conceptual profile for the concept. Multiple profiles are
different assessable capabilities: select one explicitly with --foundation
<capability-id> (repeat for distinct concepts), or narrow the target. Never union
successful dimensions or choose an optimistic grade across profiles. --foundation
must name a conceptual profile in the required closure. Resolve transfer/application
ambiguity by selecting that specific capability as the target in a new plan.

The selected profile's required dimensions define the bounded conceptual objective.
With no profile check explanation as a minimal working objective; that is a plan,
not creation of a record or a universal readiness rule. Recognition alone still
calls for meaningful reconstruction. Keep required derivation separate from
explanation; not every concept needs derivation. Existing explicit capability
prerequisite readiness remains authoritative, including legacy prerequisites and
profiles requiring another scope. Inspect those separately; do not relabel them.

| Required scope/dimension evidence | Next teaching decision |
|---|---|
| Unknown/missing/legacy scope | Probe before explaining; infer neither mastery nor forgetting. |
| Stale or no recorded review horizon | Check before reteaching; uncertain freshness is not proven loss. |
| Learning/fragile | Repair the observed gap, then ask for reconstruction. |
| Demonstrated/retained with a current recorded horizon | Skip automatic reteaching of that dimension. |
| Conceptual dimensions current, transfer weak/unknown | Independent transfer probe or repair. |
| Conceptual and transfer evidence current | Actual project application, when relevant. |
| Required application evidence current in this exact context | No automatic reteaching; deepen for a new goal or learner request. |

Actions are prerequisite_probe/repair, conceptual_probe/repair, transfer_probe/repair,
project_application, choose_capability, map_concepts or complete. Concept relations
order lessons but never supply grades. A prerequisite_probe may name an explicit
capability with a non-conceptual profile; inspect that contract separately.

Transfer uses the sole dedicated transfer capability when present, or the selected
conceptual ledger's explicit transfer dimension. This selects an evidence source;
it never converts conceptual success or merges profiles. Application uses its
selected profile and only attempts whose Context exactly matches the requested
project/block. A sibling block, other project or project-wide attempt cannot prove
an untested block. Application success supplies neither general theory nor transfer.

## Teach flexibly, then transfer

Prefer this progression, omitting stages already evidenced or irrelevant:

1. Check necessary prerequisites within the existing diagnostic budget.
2. Explain the general concept and connect it to established foundations.
3. Build an intuitive model or simple non-project example.
4. Add formal/mathematical treatment when needed; define objects, assumptions,
   validity limits and notation first.
5. Ask a concept-level reconstruction probe.
6. Test independent transfer to another appropriate object or situation.
7. Apply understanding to the active project and its specific assumptions.

This is not a mandatory seven-question script. Count prerequisite and concept
diagnostic questions together under the existing 3–5 default/approximately 8 upper
budget; do not evade it with renamed blocks or multipart questions. Skip current
evidence; repair only actual gaps. The learner may request deeper theory or direct
practical assistance; explain what remains untested without claiming mastery.

A project example can motivate theory but cannot be the only explanation. For box
counting in an ECAL task, plan scale invariance, what dimension measures, a simple
geometric object, relevant finite-resolution limits, another object for transfer,
then detector application. Verify the scientific content under `SOURCE_POLICY.md`;
the planner provides no scientific facts, formulas, answers or validity guarantees.

Transfer needs genuinely independent reasoning. Renaming the detector image,
changing constants or repeating a revealed solution is insufficient. Choose a
suitable example outside the active project context with the needed structural
similarity and appropriate prerequisites/difficulty. Preserve TESTS / ASSUMES /
INTRODUCES, terminology checks, verified source preparation and visuals, one
question at a time and the fast response loop.

## Record actual attempts

Before each question declare scope, dimension, method and Context internally along
with its question contract. `scripts/tutor_contract.py` supplies
scoped_question_issues to check compatible declarations and an explicit independent
example flag for transfer. It cannot inspect wording, scientific validity or actual
novelty; the tutor must. Definitions, visuals, lesson completion, planner actions
and learning-goal checkboxes are not retrieval evidence.

At block end preserve the actual learner answer, verdict and assistance. For
schema 2 append an eleven-cell row under the existing Retrieval history contract:
Date, Learning period, Timing, Method, Outcome, Assistance, Evidence, Next review,
Scope, Dimension, Context. Use conceptual/empty Context for general reasoning,
transfer/transfer/empty Context for an independent example, and project_application
with the exact project/block ID for project reasoning. Record the dimension actually
tested, honest failure/partial outcomes and assistance. Never duplicate a project
answer into conceptual/transfer rows. Deliberate multi-capability questions require
separately attributable answers/verdicts, not copies of one grade.

Write only to the intended working ledger within the authorized workflow, then
validate through the existing parser/knowledge query. With no ledger propose/create
an explicit profile under that workflow; the planner's fallback is not a migration.
Keep earlier attempts; same-session retries are not delayed retention. Retention
targets and scheduling are unchanged. Never resolve a research question from mastery.

Schema-1 targets keep graph-first scalar readiness with unknown conceptual/transfer
scope. Explicit reviewed migration or new scoped attempts are needed for new claims.
Old sessions still work. The template adds optional conceptual/transfer/application
prompts without changing section numbers or checkbox submission. Existing notes
are not rewritten. Both providers receive the same helper and references on install.
