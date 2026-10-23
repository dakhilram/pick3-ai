"""Official Texas Pick 3 drawing times in America/Chicago (Monday-Saturday)."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

CENTRAL = ZoneInfo('America/Chicago')
HOUSTON = CENTRAL
DRAW_TIMES = {'morning': (10, 0), 'day': (12, 27),
              'evening': (18, 0), 'night': (22, 12)}
# Compatibility helpers for the legacy lightweight test suite. Production
# checks run on every scheduled Actions invocation, including delayed starts.
CHECKS = ((10, 6), (12, 33), (18, 6), (22, 18))


def should_check(when, event='schedule'):
    if event != 'schedule':
        return True
    local = when.astimezone(CENTRAL)
    minute = local.hour * 60 + local.minute
    return local.weekday() != 6 and any(0 <= minute - (hour * 60 + part) <= 24
                                        for hour, part in CHECKS)


def scheduled_at(session, day):
    if session not in DRAW_TIMES:
        raise ValueError(session)
    if isinstance(day, str):
        day = date.fromisoformat(day)
    hour, minute = DRAW_TIMES[session]
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=CENTRAL)


def next_draw(session, after):
    local = after.astimezone(CENTRAL)
    day = local.date()
    for offset in range(8):
        candidate = day + timedelta(days=offset)
        if candidate.weekday() == 6:
            continue
        instant = scheduled_at(session, candidate)
        if instant > local:
            return instant
    raise RuntimeError('No upcoming draw found')
