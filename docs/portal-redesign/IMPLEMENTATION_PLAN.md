# Portal implementation ledger

Execute in dependency order, concurrency one. Do not promote, push, deploy or alter live vaults.
Each row is a bounded slice; gates and actual outcomes belong in REPORT.md.

| Slice | Owns | Depends on | Acceptance |
|---|---|---|---|
| S0 Baseline | `docs/portal-redesign/*`, characterization fixtures | none | Record revision, baseline checks, rollback and ADR |
| S1 Reading workspace | `frontend/*`, `ros/portal/workspace/*`, `ros/serve.py`, packaging, new browser tests | S0 | Real handout and lesson log from existing API; math, GFM, safe URLs; 7 widths; old portal passes |
| S2 References | indexed domain adapter, tool declaration, typed client, inspector | S1 | Cross-record ids, stable section links, backlinks, missing/ambiguous resolution; no vault scan per click |
| S3 Graph | focused subgraph adapter, graph view, benchmark | S2 | Bounded typed directed relationships; pan/zoom, filters, list fallback, node-to-evidence |
| S4 Workflows | Learn/Research components and API contracts | S3 | Real backend lesson steps, pending grades, evidence and human action boundary; drafts preserved |
| S5 Standalone/notes | optional note projection adapter, export, docs | S4 | No-vault reading; safe links; immutable originals preserved |
| S6 Hardening | tests, CI, report and rollback guide | prior accepted slices | Full domain + browser gates, explicit limitations, committed resumable milestone |

Budget checkpoint after S1: inspect dependency/build sizes, checks and elapsed time before expanding.
No paid provider invocation is authorized by this plan. `eng doctor`, providers and plan validation are
conditional on eng being installed. It was absent at baseline and became available later. Its doctor/providers
preflight now confirms CLI executables only, not account access. `pilot-plan.yaml` is a bounded S0/S1 acceptance
plan for independent review; it is validated without creating or executing an eng plan. No provider sessions
or plan promotion are authorized by that validation. Usage thresholds are not a hard credit cap. Never recursively invoke eng.

Required baseline/release commands:

```sh
python -m unittest discover -s tests -p "test_*.py"
node tests/ros-portal-browser.cjs
cd frontend
npm ci
npm test
npm run build
```

Windows: set `PYTHON=python`, `ROS_PLAYWRIGHT` to the available module and `ROS_BROWSER` to Chrome.
Browser tests use temporary fixture records, never live records. An environment failure is recorded separately
from a product assertion failure. Inspect the actual diff and commit each tested milestone on the integration branch.
