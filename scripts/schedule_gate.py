"""Gate UTC GitHub schedule runs against Houston draw-followup windows."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import os

HOUSTON = ZoneInfo("America/Chicago")
# Draws: 10:00, 12:27, 18:00, 22:12 Central Mon-Sat.
# Two checks per draw allow time for official CSV publication.
CHECKS = ((10,35),(11,15),(13,5),(13,45),(18,35),(19,15),(22,45),(23,25))

def should_check(when, event="schedule"):
    if event != "schedule":
        return True
    local = when.astimezone(HOUSTON)
    if local.weekday() == 6:
        return False
    now_minutes = local.hour * 60 + local.minute
    return any(0 <= now_minutes - (hour*60 + minute) <= 24
               for hour, minute in CHECKS)

if __name__ == "__main__":
    now = datetime.now(timezone.utc)
    event = os.environ.get("GITHUB_EVENT_NAME", "schedule")
    allowed = should_check(now, event)
    local = now.astimezone(HOUSTON)
    train = event != "schedule" or (local.hour == 23 and local.minute >= 25)
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as out:
            out.write(f"run={'true' if allowed else 'false'}\n")
    print(f"Houston {local.isoformat()}; {event}; update={allowed}; train={train}")
