"""What a configured provider profile may do and where its data goes, decided from the real transport. Standard library only.

Used by the runtime at dispatch: ``is_local`` (may this run read local-only sources?) re-parses the actual endpoint and never
trusts a model-name prefix or a stored label; ``require`` refuses a run whose required capabilities the profile does not
have; ``check_result`` holds a custom agent's final report to its declared result schema. See
docs/core-experience/PROVIDERS.md.
"""
from __future__ import annotations

from urllib.parse import urlparse

from .providers import ProviderError

LOOPBACK = ('127.0.0.1', 'localhost', '::1')
LOCAL_PROVIDERS = ('ollama', 'compatible')
DEFAULT_ENDPOINTS = {'ollama': 'http://127.0.0.1:11434', 'compatible': 'http://127.0.0.1:1234/v1'}
# What each adapter can do at all. For HTTP models, tools and vision also need the person's declaration on the profile.
ADAPTER = {
    'codex': frozenset({'streaming', 'tools', 'vision', 'cancel'}),
    'claude': frozenset({'streaming', 'tools', 'vision', 'cancel'}),
    'ollama': frozenset({'streaming', 'tools', 'vision', 'cancel'}),
    'compatible': frozenset({'streaming', 'tools', 'vision', 'cancel'}),
    'api': frozenset({'streaming', 'tools', 'vision', 'cancel'}),
}
DECLARED = ('tools', 'vision')  # needs the profile's own flag for HTTP models
CAPABILITIES = ('streaming', 'tools', 'vision', 'cancel')


class CapabilityMissing(ProviderError):
    """The selected profile lacks a capability the work requires. Nothing was sent; no other provider was chosen instead."""
    code = 'capability_missing'


class AgentResultInvalid(ValueError):
    """A custom agent's final report does not match its declared result schema; nothing is inferred from it."""
    code = 'agent_result_invalid'


def provider_of(model: str, profile: dict | None) -> str:
    return (profile or {}).get('provider') or str(model).split(':', 1)[0]


def is_local(model: str, profile: dict | None) -> bool:
    """Whether this run's data stays on this computer: a local adapter whose actual endpoint is plain-HTTP loopback. A remote
    API profile is never local (even on a loopback address), a subscription CLI never is, and neither is an unknown name."""
    provider = provider_of(model, profile)
    if provider not in LOCAL_PROVIDERS: return False
    endpoint = (profile or {}).get('endpoint') or DEFAULT_ENDPOINTS[provider]
    try: parsed = urlparse(endpoint)
    except ValueError: return False
    return parsed.scheme == 'http' and parsed.hostname in LOOPBACK and not parsed.username and not parsed.password


def supported(profile: dict) -> set:
    provider = profile.get('provider')
    have = set(ADAPTER.get(provider, ()))
    if provider in ('ollama', 'compatible', 'api'):
        have -= {name for name in DECLARED if not profile.get(name)}
    elif provider in ('codex', 'claude') and not profile.get('vision'):
        have.discard('vision')  # images go only to a profile whose vision the person verified
    return have


def require(profile: dict | None, needs) -> None:
    needs = sorted(set(needs or ()))
    if not profile:
        raise CapabilityMissing('No provider profile is configured for this work; configure one first. Nothing was sent.')
    missing = [name for name in needs if name not in supported(profile)]
    if missing:
        raise CapabilityMissing(f"The profile {profile.get('id', '?')} does not provide {', '.join(missing)}, which this work requires. "
                                'Nothing was sent and no other provider was chosen.')


TYPES = {'string': str, 'number': (int, float), 'integer': int, 'boolean': bool, 'array': list, 'object': dict}


def check_result(schema: dict, value) -> None:
    """``value`` against the small JSON-schema subset a manifest may declare: an object with typed properties, required keys and
    optionally no additional properties."""
    def kind(name, item):
        expected = TYPES[name]
        if isinstance(item, bool) and name in ('number', 'integer'): return False
        return isinstance(item, expected)
    if not isinstance(value, dict):
        raise AgentResultInvalid('The agent did not return a JSON object as its result schema requires.')
    properties = schema.get('properties', {})
    missing = [k for k in schema.get('required', []) if k not in value]
    if missing: raise AgentResultInvalid('The agent result lacks required fields: ' + ', '.join(missing) + '.')
    for key, item in value.items():
        if key not in properties:
            if schema.get('additionalProperties', True) is False: raise AgentResultInvalid(f'The agent result has an undeclared field {key[:60]!r}.')
            continue
        if not kind(properties[key]['type'], item): raise AgentResultInvalid(f"The agent result field {key!r} is not {properties[key]['type']}.")
