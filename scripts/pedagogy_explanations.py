"""Pure presentation projection for validated P1 explanation entries.

Source declarations are preserved, not independently verified here. Selection
checkpoints do not award evidence and never alter lecture progress.
"""
from copy import deepcopy

LEVELS = ('intuitive', 'intermediate', 'formal')


def project(entry, events=None, requested=None, preferred=None):
    """Select only a prepared variant, restoring this entry/version's last choice.

    An unavailable explicit request reports that fact and retains the restored
    selection. Input must already have passed pedagogy_contract.validate.
    """
    levels = entry.get('levels') or {}
    available = [level for level in LEVELS if level in levels]
    selected = preferred if preferred in available else (available[0] if available else None)
    restored = False
    prefix = f"pedagogy-level:{entry['id']}:{entry['version']}:"
    for event in events or []:
        response = event.get('response') if isinstance(event, dict) else None
        if (isinstance(event, dict) and event.get('type') == 'checkpoint' and event.get('question_id') is None
                and isinstance(response, str) and response.startswith(prefix)
                and response[len(prefix):] in available):
            selected = response[len(prefix):]
            restored = True
    unavailable = preferred if preferred is not None and preferred not in available and not restored else None
    if requested is not None:
        unavailable = requested if requested not in available else None
    if requested in available:
        selected = requested
    return {'entry_id': entry['id'], 'version': entry['version'],
            'available': available, 'selected': selected,
            'variant': deepcopy(levels.get(selected)),
            'sources': deepcopy(entry.get('sources', [])),
            'unavailable': unavailable}
