# Authenticated scholarly access protocol

Status: Slice 2 local handoff capability implemented in `scripts/paper_access.py`.
`PAPER_LIBRARY.md` continues to own screened bibliographic storage and
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

## Versioned access outcome

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

Slice 2 tests use fake/local fixtures only: authorized handoff, missing/expired
session, denial, prohibited automation, manual retrieval, OA fallback, duplicate
library paper, secret rejection/redaction, safe logs, path escapes and rate/bulk
limits. No live credentials, publisher sessions or institutional data are fixtures.

## Runtime and provider contract

Use `paper_access.py --root <library> --inbox <inbox> --input <sanitized-request.json>`.
It plans by default; `--apply` authorizes local writes/imports. Reviewed public OA
fallback additionally requires `--download`; authenticated service operations are
never performed by this helper. No password/session/configuration field exists.
Both provider bundles contain the same helper and protocols. An upstream capability
must return only one already sanitized outcome/document; never export a raw provider
response for an agent to redact. Provider session tooling stays outside Research OS.

The schema-1 request contains reviewed `paper` metadata without `pdf`, an explicit
`source_version`, optional `result`, and at most one `open_fallback`. The result has
exactly `status`, `identity`, `source_version`, `basis`, `source_origin`, `method`,
`automation`, and `local_file` only for an available document. Identity must match a
reviewed paper alias; version must match the request. Source origin is HTTPS host
only. Unknown fields, recognizable credential strings, URL userinfo, queries,
fragments and encoded URL strings are rejected, with fixed CLI errors and no echo.
An opaque secret disguised as metadata cannot be detected mechanically; upstream
sanitization and selecting only scholarly documents are required.

Supported status codes: `available`, `missing-session`, `expired-session`,
`access-denied`, `automation-prohibited`, `manual-required`, `metadata-only`,
`retrieval-failed`, `rate-limited`, `version-unconfirmed`. Supported result methods:
`broker-local`, `manual-inbox`, `local-inbox`. Broker/local automated handoffs require
explicit permission `allowed`; `unknown`/`prohibited` yields manual retrieval.
A `manual-inbox` handoff has basis `manual` and preserves the declared automation
permission without using it as authorization to operate a service.

Public OA fallback is one reviewed URL with explicit `automation: allowed` and
matching version. HTTPS/public URL validation and robots policy apply to each PDF
redirect, and public URL validation applies to robots redirects. Download errors
become a fixed `retrieval-failed` code. Retrieval URLs/diagnostics are never cataloged by
this helper; the record retains origin only. Robots 404 is allowed; denied or unknown
policy fails closed. A session is never forwarded to this downloader.

Documents are bounded at 50 MiB, confined to a selected inbox without symlinks,
checked for PDF header and staged for existing authorized-local ingestion. Screening
remains authoritative: only useful papers gain canonical PDFs. Metadata-only entries
can retain access gaps; this helper does not grade usefulness or accept claims.
One access lock guards writes/retrieval, alongside existing ingestion locking.
Attempts are bounded to one per minute and ten per rolling day in a per-library
file, including failed attempts. This is not an account-wide/global rate guarantee.
Cache hits validate hash and version-bound sidecar before returning an idempotent
outcome; older cached PDFs without such provenance require explicit manual review.

Records in `.access/PAPER-<id>.access.json` bind canonical paper ID, identity and
document version to a confined path and SHA-256. Add `access_ref` with `record_ref`
and `document_ref` to a literature claim, both relative to its check root; permitted
copies can be explicitly placed under a project root. The checker validates the
record/document and retains provenance in factual/qualified exports and minimal
verifier handoffs, rechecking on handoff. Retrieval never sets reading depth or
creates receipts. Older literature manifests without references remain supported;
the original paper-library parser and EvidenceAtom schema are unchanged.

See `examples/access/README.md` for a runnable plan and limitations. No active
institutional/browser integration is claimed. Record assertions and hashes do not
prove entitlement, document identity from its contents, independence or scientific
truth; those require the external broker and source review.
