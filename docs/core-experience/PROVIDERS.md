# Providers, credentials and custom agents (S4)

Version 1, backend only. People can run Research OS with their own subscription CLI login, their own remote API key or a
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
  The older one-shot reply path in `ros/lib/dialogue.py`, used by the portal's "Reply exactly READY" connection check,
  still inherits the full environment (see the follow-ups).
- **No fallback.** If a credential is missing or refused, or a required capability is absent, the run stops. No other
  profile, provider or key is tried.
- **No invented cost.** The remote adapter returns `{"usage": <as reported by the service or null>, "cost": null}`.
  `run.usage` records only what an adapter reports. A Claude Code result's own `total_cost_usd` is passed through unchanged.
- **Retries.** A transient failure (a dropped connection, or HTTP 500, 502, 503, 504 or 529) is retried by
  `runtime.execute` up to 3 times on the same provider. A retry of a remote request is a new request to the same paid
  service. HTTP 429 is never retried automatically.
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
  `vision`, `context_limit` and, new in this slice, `credential` (a reference object).
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
  removes the exact key from tool results before they go back to the model, and from every error message. The runtime
  removes it from tool results before they are recorded as run steps (`runtime.redact`). Remote error bodies are never
  quoted; only the HTTP status is.
- **Platforms without a Credential Manager.** On a non-Windows platform, or where advapi32 is missing, the `os` store
  reports `unavailable` (`CredentialUnavailable`). It never silently falls back to `env`.
- **Not yet covered.** Writing a key into the OS store is the desktop host's or a person's act; it has no agent tool. The
  surface for it is a follow-up, listed below.

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
| `credentials.CredentialInvalid` | `credential_reference_invalid` | The reference is not `{store, name}` or the name is not allowed. The input is never echoed. |
| `credentials.CredentialMissing` | `credential_missing` | Absent, empty or revoked. Nothing was sent; no fallback. |
| `credentials.CredentialUnavailable` | `credential_store_unavailable` | The OS credential store does not exist here or refused the operation. |
| `providers.ProviderAuthError` | `provider_auth` | HTTP 401/403 from the remote API. Replace or check the key. |
| `providers.ProviderLimitError` | `provider_limit` | HTTP 429. Not retried automatically. |
| `providers.TransientProviderError` | `provider_transient` | The connection dropped or the service is overloaded. Retried on the same provider. |
| `providers.ProviderError` | `provider_error` | A malformed or unfinished stream, a refused redirect, or a remote endpoint that is not HTTPS. |
| `provider_profiles.CapabilityMissing` | `capability_missing` | The profile lacks a required capability, or no profile is configured. |
| `provider_profiles.AgentResultInvalid` | `agent_result_invalid` | A custom agent's result is not one JSON object matching its schema. |

All of these are `ValueError`s, so the existing CLI, MCP and HTTP error envelopes and the run's `failed` state carry them.

## Follow-ups outside this slice's files

- **`api:` models in chats.** `ros/conversation.py`, `ros/serve.py`, `ros/home.py` and `ros/lib/dialogue.py` still accept
  only `(codex|claude|ollama|compatible):` model ids, so a chat cannot yet select an `api:` model. It is refused, which
  fails safe. The runtime routing is in place and tested by driving `runtime.execute` directly.
- **Defining an agent.** This needs a human tool `agent_define`, and adding it requires changing the pinned human-tool set
  in `tests/test_ros_m6.py`. Today, `execution.agent_define` is domain-only and runs are started with
  `runtime.run_custom_agent`.
- **Connection check.** `ros/lib/dialogue.py`'s one-shot CLI reply path should launch with `providers.subscription_env()`.
  It is not in this slice's files.
- **Contracts.** `docs/core-experience/CONTRACTS.md` should record the v2 profile, credential reference and manifest
  schemas once they are reviewed.
- **Desktop surface.** The desktop needs a UI to write and revoke `ResearchOS:` credential entries and to show
  `credentials.status` (present, missing or unavailable) without the value.
- **Documentation updates.**
  - `references/DATA_MODEL.md` should document the `agent.defined` event and the `credential` field of
    `provider.configured`.
  - `docs/ARCHITECTURE.md` should describe the provider recipe for remote profiles, credential references and custom agents.
