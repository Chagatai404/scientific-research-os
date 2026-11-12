# Providers, credentials and custom agents (S4)

Version 1 (backend in S4; chats, App settings and key entry in S4b). People can run Research OS with their own subscription CLI login, their own remote API key or a
model on their own computer, and they can define their own agents. This document describes what the code does and how
much of it has been verified. No live provider call was made for this slice. Everything marked `tested` below was run
against deterministic fixtures (scripted processes, a monkeypatched HTTPS transport and loopback test servers). Nothing is
`live-verified` yet.

## Three kinds of provider

| Provider id | Kind | Auth | Transport | Local-only sources | Streaming | Tools | Vision | Cancel |
|---|---|---|---|---|---|---|---|---|
| `codex:<model>` | subscription | `cli_login` (the person's Codex login) | `cli` (app-server over stdio) | never | tested | tested | tested | tested |
| `claude:<model>` | subscription | `cli_login` (the person's Claude Code login) | `cli` (stream-json) | never | tested | tested (MCP bridge) | tested | tested |
| `ollama:<model>` | local | `none` | `local_loopback` (HTTP to 127.0.0.1, localhost or ::1) | yes, if the real endpoint is loopback | tested | tested | declared | tested |
| `compatible:<model>` | local | `none`, or `api_key` when a credential reference is set (else the legacy `ROS_LOCAL_API_KEY` variable) | `local_loopback` | yes, if the real endpoint is loopback | tested | tested | declared | tested |
| `api:<model>` | remote | `api_key` (credential reference required) | `remote_https` (OpenAI-compatible `POST <endpoint>/chat/completions`, server-sent events) | never, even on a loopback address | tested | tested | declared | tested |

The status values are `declared` (implemented, no fixture), `tested` (a deterministic fixture exercises it),
`live-verified` (a recorded, bounded smoke against the real service) and `unsupported`. The matrix is
`execution.EVIDENCE`, readable through the `provider_capabilities` tool. Fixture evidence:
`tests/test_ros_provider_protocols.py`, `tests/test_ros_provider_profiles.py`, `tests/test_ros_custom_agents.py`
(AC12 matrix), `tests/test_ros_local_provider.py` and `tests/test_ros_network.py`. Ollama and compatible share the
streaming loop (`providers._chat`) with the remote adapter, so its cancellation, malformed-stream and tool-result fixtures
cover all three.

What still needs a live smoke, with the person's own credentials and an agreed usage bound:

- **Codex and Claude Code:** a current CLI version with a subscription login, confirming that no API key is used.
- **Remote API:** one real OpenAI-compatible service, testing streaming, a tool call, a 401 response for a revoked key and a 429 response.
- **Ollama and an OpenAI-compatible local server:** one tool-capable model, and vision with an image.
- **Windows Credential Manager:** a reference created by the desktop host. The adapter itself is tested against a uuid-named test entry that it writes and then deletes.

Rules that hold for every kind:

- **No silent switch to paid billing.** The session, role, dispatch and Code-session adapters (`providers.codex` and
  `providers.claude`) start their CLI child without `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `OPENAI_API_KEY`,
  `CODEX_API_KEY`, `CLAUDE_CODE_USE_BEDROCK` or `CLAUDE_CODE_USE_VERTEX` (`providers.PAID_ENV`,
  `providers.subscription_env`, also the default environment of `providers.launch`). A key that happens to be set therefore cannot turn a login-based run into an API-billed
  one. This document does not claim which variable each CLI prefers; the variables are removed so that it cannot happen.
  The one-shot reply path in `ros/lib/dialogue.py`, used by the portal's "Reply exactly READY" connection check, passes the same
  scrubbed environment (`providers.subscription_env()`) whenever a paid variable is set. With none set nothing would change, so it
  inherits the environment as before.
- **A key a profile points to never reaches a child process.** A profile `{store: env, name: MY_LLM_KEY}` keeps its key in this
  process's environment, where the in-process HTTP adapters read it. Every child this program starts gets its environment from one
  builder, `credentials.child_env` (`providers.subscription_env` is the same call): this process's environment without `PAID_ENV`,
  without `ROS_LOCAL_API_KEY` and without every variable named by an `env` reference of any profile read in this process
  (`runtime.note_profiles` reads them; it runs at the start of every run, agent task, engine process and connection check, and
  `child_env` hides what was noted). That covers the Codex and Claude Code children (including a Code session's own shell), the job
  runner (`runner.BEFORE_JOB` reads the record's profiles before each job), engine processes, the dialogue worker, the safe renderer's probe and build, animation scenes, the PDF build and the
  notebook runner. The one exception is the dialogue worker of a connection check: it keeps the single variable its own request
  refers to (or `ROS_LOCAL_API_KEY` for a `compatible:` profile without a reference), because it reads that key itself. Names are compared case-insensitively. The set only grows while the process lives. A
  process that has read no profile yet (for example a one-off command that builds a PDF before any run) knows only `PAID_ENV` and
  `ROS_LOCAL_API_KEY`. The voice engine's child (`ros/lib/voice.py`) still builds its environment itself.
- **No fallback.** If a credential is missing or refused, or a required capability is absent, the run stops. No other
  profile, provider or key is tried.
- **No invented cost.** The remote adapter returns `{"usage": <as reported by the service or null>, "cost": null}`.
  `run.usage` records only what an adapter reports. A Claude Code result's own `total_cost_usd` is passed through unchanged.
- **Retries.** A transient failure (a dropped connection, or HTTP 500, 502, 503, 504 or 529) is retried by
  `runtime.execute` up to 3 times on the same provider. A retry of a remote request is a new request to the same paid
  service. HTTP 429 is never retried automatically. A timeout after the request was sent (the service may still be working on it) is
  retried at most once (`TransientProviderError.retry_limit`); a timeout while connecting sent nothing and keeps the three retries.
- **Certificates.** A certificate that is not trusted (`ssl.SSLCertVerificationError`, bare or wrapped in a `URLError`, or an
  `ssl.SSLError` that names the certificate) is a plain `ProviderError` ("certificate not trusted"), never transient and never
  retried: asking again cannot help, and the key was not sent. Other TLS errors, such as a connection cut mid-stream, stay transient.
- **Unattended tasks.** A timeout after the request was sent also ends an agent task as `failed` (not `interrupted`, which the
  dispatcher would take again), so the request is not repeated at the service's expense.
- **Reply bound and usage.** The request bounds the reply with `max_tokens`, or with `max_completion_tokens` when the profile says so
  (`token_param`, set through `execution.configure`) or when the endpoint host is `api.openai.com`, whose newer models refuse
  `max_tokens`. Ollama's own protocol sends neither. `api` and `compatible` requests also send
  `stream_options: {include_usage: true}` so that the final chunk reports usage; a later chunk with `usage: null` never overwrites
  usage already collected.
- **Remote transport.** HTTPS only, with the default certificate verification. Environment proxies are ignored. Any
  redirect is refused, so the `Authorization` header can never follow a redirect to another host. Credentials embedded in
  the URL, query strings and fragments are refused.

## Profile schema (`ros.provider-profile.v2`)

A profile is written by the human `provider_configure` tool as a `provider.configured` event. `provider_profiles` returns it
as follows:

```json
{"schema": "ros.provider-profile.v2", "id": "api:my-model", "provider": "api", "kind": "remote", "auth": "api_key",
 "transport": "remote_https", "endpoint": "https://api.example.org/v1", "model": "my-model", "tools": true, "vision": false,
 "context_limit": 16000, "credential": {"store": "env", "name": "MY_API_KEY"},
 "capabilities": {"streaming": true, "tools": true, "vision": false, "cancel": true}, "revision": "<sha256 of the fields above>"}
```

- **`provider_configure`** takes `provider` (`ollama | compatible | codex | claude | api`), `endpoint`, `model`, `tools`,
  `vision`, `context_limit`, `credential` (a reference object) and, in `execution.configure`, the optional `token_param`
  (`max_tokens` or `max_completion_tokens`, `api` and `compatible` only; a profile that does not set it is unchanged and keeps its
  revision). The `provider_configure` tool does not expose `token_param` yet.
  - `api` needs an `https://` endpoint and a credential reference.
  - `codex` and `claude` refuse both an endpoint and a credential.
  - `ollama` refuses a credential.
  - `compatible` takes an optional reference.
- **Older events.** v1 `provider.configured` events fold into the same v2 shape deterministically. Profiles are compared by
  equality in vision permissions, so live credential status is never part of a profile.
- **`kind` is a label only.** Whether a run may read local-only sources is decided at dispatch by
  `provider_profiles.is_local(model, profile)`. It re-parses the actual endpoint: only `ollama` and `compatible` with a
  plain-HTTP loopback endpoint count as local. A remote, subscription, unknown or `agent:` name is never local. The runtime
  uses this decision for `source_refusal`, `source_result`, the cloud guard, delegated roles, unattended dispatch and custom
  agents.
- **`provider_capabilities`** returns `{"schema": "ros.provider-capabilities.v1", "statuses", "adapters", "profiles"}`. It
  contains no credential status and no value.

## Credential references (`ros/lib/credentials.py`)

- **The shape is exactly `{"store": "env" | "os", "name": ...}`.**
  - `env`: a variable name matching `[A-Z_][A-Z0-9_]{0,63}`. Used for headless runs, read from the process that executes the work.
  - `os`: a name in the `ResearchOS:` namespace matching `ResearchOS:[A-Za-z0-9][A-Za-z0-9_.-]{0,99}`. Used on the desktop: a
    Windows Credential Manager generic credential written by `os_store_write`.
  - Any other field (such as `value`), a key-shaped name, or a name outside the namespace is refused, and the error never
    repeats the input. A name outside the namespace is refused before the store is touched.
- **Resolution happens only at dispatch** (`runtime.bind_credential`), every time, with no cache. A replaced key is used on
  the next run. A revoked key (variable unset, or entry deleted with `os_store_delete`) stops the next run with
  `CredentialMissing`.
- **The value in memory.** The resolved value is a `credentials.Secret`. It prints as `[credential]`, refuses JSON and
  pickling, and is revealed only to the adapter that builds the `Authorization` header.
- **Where the key never appears:** events, profiles, manifests, exports, model context, tool results and logs. The adapter
  removes the key from tool results before they go back to the model, and from every error message. The runtime
  removes it from tool results before they are recorded as run steps (`runtime.redact`). Remote error bodies are never
  quoted; only the HTTP status is.
  - **Every spelling is scrubbed.** `credentials.scrub` replaces the value as it is and as JSON writes it (escaped quotes and
    backslashes, control characters, non-ASCII with and without escapes), longest first.
  - **Scrub, then shorten.** A text is scrubbed before it is cut to its display length, so a key that straddles the cut is not left
    half visible.
  - **No short keys.** A value under 4 characters cannot be told from ordinary text, so it cannot be scrubbed safely. `resolve`
    refuses it (`CredentialInvalid`, status `invalid`), and `os_store_write` refuses to store one.
  - **Windows blobs.** `credentials.decode_blob` reads a stored blob as UTF-8 (what Research OS writes) or UTF-16LE (what `cmdkey`
    and other programs write, with or without a byte-order mark), drops trailing NULs, and otherwise stops with "store it again"
    without repeating the bytes.
- **Platforms without a Credential Manager.** On a non-Windows platform, or where advapi32 is missing, the `os` store
  reports `unavailable` (`CredentialUnavailable`). It never silently falls back to `env`.
- **Entering a key (S4b).** Writing a key into the OS store is the person's act and has no tool. The paired browser posts to
  `/services/credential` with `operation` `set`, `delete` or `status`. `set` and `delete` take a name in the `ResearchOS:` namespace;
  `status` takes any reference. The key is in that request body and then on the stdin of the `ros.lib.dialogue` worker, which calls
  `credentials.os_store_write`. The answer is `{name, store, status}` and never the value, no event is appended, refusals never
  repeat the input, and the Settings key field is cleared as soon as the key is sent. No CLI or MCP tool takes a key: a headless user
  sets an environment variable and uses an `env` reference.

## Custom agents (`ros.agent-manifest.v1`)

A manifest has exactly these fields: `id` (`agent:<lowercase-name>`), `version` (an integer of 1 or more), `title`,
`instructions` (up to 20,000 characters), `base`, `tools`, `profile` (a configured provider profile id), `result_schema`,
`limits` and `requires`.

- **Tools only narrow.** `base` is `role:<scout|verifier|adversary|librarian>` or `mode:<name>`, and `tools` must be a
  subset of that grant.
- **Tools a manifest can never hold.** A manifest never holds a registry human tool, nor anything in
  `modes.AGENT_DENIED`:
  - approvals, decisions, waivers, verdicts, grades and delegation;
  - the person's settings tools;
  - the tools that record the learner's words (`answer`, `ask`, `reply`, `pedagogy_reply`, `engage`), because an agent
    run has no learner message to bind them to.
- **No authority or credential fields.** A manifest cannot add `authority`, `grants`, `credential` or any other field.
  Instructions or titles that look like a key or a credential assignment are refused, and the error does not repeat them.
- **`limits`.** Allowed keys are `tool_steps`, `deadline`, `output` and `provider_calls`. At run time each is reduced to
  the workspace limit with `min()`.
- **`requires`.** A subset of `streaming`, `tools`, `vision` and `cancel`. `tools` is added automatically when tools are
  granted.
- **`result_schema`.** An object schema whose properties are typed (`string`, `number`, `integer`, `boolean`, `array` or
  `object`), with `required` names and `additionalProperties` set to true or false.
- **Hash and versions.** The `hash` is the SHA-256 of the canonical normalised manifest. `execution.agent_define`
  appends `agent.defined` with subject `agent:<name>@<version>` and actor `person`.
  - The same content again is a no-op.
  - Different content under an existing version is refused, so a version is immutable.
  - The first event of a version is authoritative.
- **Verification before a run.** `agent_get` reports `verified`. `agent_dispatch` refuses a manifest whose hash or rules
  no longer verify.
- **`runtime.run_custom_agent(rec, agent, brief, version=None, entry=None)`** does the following:
  1. Resolves the configured profile and refuses missing capabilities (`CapabilityMissing`) before any call.
  2. Applies the cloud guard to non-local transports.
  3. Allows only the narrowed, non-human tools, re-checked on every call.
  4. Refuses local-only sources unless the real transport is loopback.
  5. Resolves the profile's credential.
  6. Parses the final message as one JSON object and checks it against the schema (`AgentResultInvalid`).

  It returns `{agent, version, hash, profile, result}`.

## Error classes

| Class | `code` | Meaning |
|---|---|---|
| `credentials.CredentialInvalid` | `credential_reference_invalid` | The reference is not `{store, name}`, the name is not allowed, or the stored value is under 4 characters. The input is never echoed. |
| `credentials.CredentialMissing` | `credential_missing` | Absent, empty or revoked. Nothing was sent; no fallback. |
| `credentials.CredentialUnavailable` | `credential_store_unavailable` | The OS credential store does not exist here or refused the operation. |
| `providers.ProviderAuthError` | `provider_auth` | HTTP 401/403 from the remote API. Replace or check the key. |
| `providers.ProviderLimitError` | `provider_limit` | HTTP 429. Not retried automatically. |
| `providers.TransientProviderError` | `provider_transient` | The connection dropped or the service is overloaded. Retried on the same provider (a timeout after the request was sent: once). |
| `providers.ProviderError` | `provider_error` | A malformed or unfinished stream, a refused redirect, a remote endpoint that is not HTTPS, or a certificate that is not trusted. |
| `provider_profiles.CapabilityMissing` | `capability_missing` | The profile lacks a required capability, or no profile is configured. |
| `provider_profiles.AgentResultInvalid` | `agent_result_invalid` | A custom agent's result is not one JSON object matching its schema. |

All of these are `ValueError`s, so the existing CLI, MCP and HTTP error envelopes and the run's `failed` state carry them.

## Using it (S4b)

- **Chats.** `conversation.send` (the App, CLI `workspace_chat_send` and MCP) accepts `api:<model>` only when a profile with that id
  and a credential reference exists. Otherwise it refuses before anything is queued ("Connect this API model in Settings first").
  A missing or revoked key is found when the run starts and fails that run clearly; no other provider is tried. Code sessions still
  need Codex or Claude Code. `agents_model` accepts `api:` ids too. Chat mode stays read-only for the graph (only learn and research
  maintain it).
- **Connection check.** `/services/model-check` accepts `api:` and passes the worker only the reference, endpoint and model.
- **Defining an agent.** The human tool `agent_define` wraps `execution.agent_define`. It is person-only, so a custom agent (whose
  tools can never include a human tool) cannot define or widen an agent. The set of human tools is computed from the tool registry by
  the tools layer and passed in; `execution.agent_define`, `agent_get` and `agent_dispatch` require it (no empty default), so a
  caller that forgets it fails instead of silently allowing a human tool. `agent_list` and `agent_get` read.
- **Settings.** *Model providers* lists each profile with its kind, transport, where its data goes (this computer, a remote
  service, your subscription), the key reference and whether the key is present, and each capability with its evidence status. It adds
  an API connection (https endpoint, model id, Windows Credential Manager or environment variable name) and replaces or removes a
  stored key. When no model works at all, Settings shows one guided choice (subscription, API key, model on this computer) instead of
  an empty list. *Custom agents* lists manifests and defines one with a base role or mode.

## Follow-ups

- **Contracts.** `docs/core-experience/CONTRACTS.md` should record the v2 profile, credential reference and manifest
  schemas once they are reviewed.
- **Live smokes.** No Settings flow, key write or `api:` chat has run against a real service or the real Credential Manager from
  the packaged App; fixtures and a patched store stand in for them.
- **Custom agent tools.** The Settings form takes tool names as text and the backend rejects any outside the base grant. It does
  not yet list a base's grant.
