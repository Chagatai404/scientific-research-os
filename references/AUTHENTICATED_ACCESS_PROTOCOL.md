# Authenticated scholarly access protocol

Status: Slice 0 design contract; capability/runtime implementation is planned for
Slice 2. `PAPER_LIBRARY.md` continues to own screened bibliographic storage and
ingestion; `SOURCE_POLICY.md` and `EVIDENCE_FORMAT.md` own scientific verification.

## Capability boundary

Canonical flow:

```text
Research OS → access broker/capability → already-authenticated user environment/session → document
```

Credentials remain external to Research OS. Agents must never know or store the
user's university password. The broker is a provider-neutral capability boundary,
not a required service, credential manager, login client or institution-specific
integration. A user-controlled authenticated browser, active authorized network,
connector, or manual retrieval may satisfy it. Research OS receives only a screened
document or a sanitized access outcome. It never receives raw session state.

Do not export, inspect or forward passwords, VPN credentials, browser cookies,
session tokens, `.env` secrets, authentication headers, institutional login forms
or private authentication artifacts. None belongs in Git, prompts, task manifests,
logs, Obsidian, paper metadata or EvidenceAtoms. The existing general agent-policy
credential exception does not apply to this scholarly-access capability.
Signed URLs and private query strings can also carry credentials: accept public
bibliographic identifiers and sanitized origin information, never raw secret URLs.
Redaction is a last safeguard; avoid receiving secrets in the first place.

## Selection and permission

Prefer existing local library → legitimate open-access copy → publisher open access
→ institutional subscription through an already-authenticated environment → author
repository/preprint → authenticated scholarly platform → manual user retrieval →
metadata-only citation with access gap. This is a search preference, not permission
to download; consider source/version suitability and permitted use at every option.

Unknown automation permission fails closed to manual retrieval. Never bypass
paywalls, CAPTCHAs, access controls or login forms, bulk-download licensed collections,
or crawl authenticated services beyond permitted use. An authorized session does
not itself authorize automation, library writes or redistribution. Maintain existing
screening and user-authorized ingestion boundaries; successful access is not usefulness.

When automation is unavailable or inappropriate, return: "Retrieve this paper
through your authenticated browser and place it in the configured paper inbox."
Do not alter VPN settings, authenticate accounts or operate external accounts as
part of implementing this capability.

## Proposed access outcome

A versioned access record should reference paper identity and document version,
access basis (open/institutional/user-session/manual/local), sanitized source,
full-text availability, retrieval method, automation permission (allowed/prohibited/
unknown), document saved/outcome, and bounded failure reason. Link a saved document
by confined path and content hash. Store no credentials or raw provider diagnostics.
Missing/expired session, access denied, automation prohibited, manual retrieval
required and metadata-only are ordinary explicit outcomes, never fabricated access.

The broker must constrain outputs to an allowlist of fields and sanitized failure
codes before persistence or agent exposure. Enforce bounded size, one requested
document at a time, rate/bulk guards, path confinement including symlinks and safe
redirect handling. Do not rely solely on scanning logs after secrets have been written.
Provider integrations must document what they can retrieve without exposing secrets.

## Compatibility and scientific use

Reuse existing authorized-local ingestion for a permitted document handoff.
Local imports still require access basis, screening, confined source paths, PDF
checks, hash protection and existing library locking/idempotence. Do not feed new
access labels into v0.7's strict PDF manifest parser until explicitly supported.
Prefer a versioned sidecar linked to catalog identity/document hash for added
provenance; preserve existing catalog outcomes and the single physical PDF model.

Access provenance must reach literature verification via explicit references.
An institutionally retrieved full text can be read and verified like any legitimate
source; access basis says nothing about scientific support. Retrieval is not reading,
reading is not independent verification, and neither accepts research conclusions.

Slice 2 tests will use fake/local fixtures only: authorized handoff, missing/expired
session, denial, prohibited automation, manual retrieval, OA fallback, duplicate
library paper, secret rejection/redaction, safe logs, path escapes and rate/bulk
limits. No live credentials, publisher sessions or institutional data are fixtures.
