"""Pure policy-day windows; callers remain responsible for receipt/bind trust.

Dates in advice and evidence retain their local policy meaning. Only the host
binding operation may mint freshness; browser consumers only check a window.
"""
from datetime import date, datetime, time, timedelta, timezone, tzinfo
import re

UTC = timezone.utc
_DAY = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}\Z')
_INSTANT = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z')


def _day(value):
    if not isinstance(value, str) or not _DAY.fullmatch(value): return None
    try: return date.fromisoformat(value)
    except ValueError: return None


def _instant(value):
    if not isinstance(value, str) or not _INSTANT.fullmatch(value): return None
    try: return datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=UTC)
    except ValueError: return None


def _now(value):
    if value is None: return datetime.now(UTC)
    if isinstance(value, str): return _instant(value)
    if isinstance(value, datetime):
        try:
            if value.tzinfo is not None and value.utcoffset() is not None: return value.astimezone(UTC)
        except (ValueError, OverflowError, OSError, TypeError): pass
    return None


def validate(window, as_of):
    """Validate bounded shape only, without claiming a trusted receipt or source."""
    if (not isinstance(window, dict) or set(window) != {'day', 'start', 'end'}
            or _day(as_of) is None or window.get('day') != as_of): return False
    start, end = _instant(window.get('start')), _instant(window.get('end'))
    return start is not None and end is not None and timedelta(0) < end - start <= timedelta(hours=48)


def is_current(window, as_of, now=None):
    """Use an absolute instant; never compare browser UTC day with policy day."""
    instant = _now(now)
    return bool(instant is not None and validate(window, as_of)
                and _instant(window['start']) <= instant < _instant(window['end']))


def _zone(value):
    if value is None or isinstance(value, tzinfo): return value
    if isinstance(value, str) and len(value) <= 100:
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(value)
        except (ValueError, KeyError, ImportError): pass
    raise ValueError('Unavailable policy timezone')


def _midnight(day, zone):
    """Resolve both folds and round-trip to reject skipped/ambiguous midnight."""
    local = datetime.combine(day, time())
    candidates = set()
    for fold in (0, 1):
        boundary = local.replace(fold=fold)
        aware = boundary.astimezone() if zone is None else boundary.replace(tzinfo=zone)
        candidate = aware.astimezone(UTC)
        back = candidate.astimezone() if zone is None else candidate.astimezone(zone)
        if back.replace(tzinfo=None, fold=0) == local:
            candidates.add(candidate)
    return candidates.pop() if len(candidates) == 1 else None


def mint(as_of, now=None, zone=None):
    """Return a window only for the actual current host-policy day.

    ``zone=None`` uses the OS local calendar; tests may supply a tzinfo or IANA
    zone without changing the PC timezone. A past explicit --as-of never gains
    freshness. Both midnight conversions are independent, preserving DST days.
    """
    day, instant = _day(as_of), _now(now)
    if day is None or instant is None: return None
    try:
        policy_zone = _zone(zone)
        local_now = instant.astimezone() if policy_zone is None else instant.astimezone(policy_zone)
        if local_now.date() != day: return None
        start, end = _midnight(day, policy_zone), _midnight(day + timedelta(days=1), policy_zone)
        if start is None or end is None or start.microsecond or end.microsecond: return None
        # strftime does not consistently pad years below 1000 on every OS.
        result = {'day': as_of, 'start': start.isoformat(timespec='seconds').replace('+00:00', 'Z'),
                  'end': end.isoformat(timespec='seconds').replace('+00:00', 'Z')}
        return result if is_current(result, as_of, instant) else None
    except (ValueError, OverflowError, OSError):
        return None
