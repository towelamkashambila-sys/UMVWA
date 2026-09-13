from __future__ import annotations
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def parse_datetime(value: str, default_tz: str = 'UTC') -> datetime:
    if not value or not isinstance(value, str):
        raise ValueError('datetime is required')
    s = value.strip().replace('Z', '+00:00')
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as e:
        raise ValueError('invalid ISO-8601 datetime') from e
    if dt.tzinfo is None:
        try: tz = ZoneInfo(default_tz)
        except Exception as e: raise ValueError('invalid timezone') from e
        dt = dt.replace(tzinfo=tz)
    return dt


def normalize_iso(value: str, default_tz: str = 'UTC') -> str:
    return parse_datetime(value, default_tz).astimezone(timezone.utc).isoformat()


def temporal_state(when: str, now: datetime | None = None, soon_hours: int = 48) -> str:
    due = parse_datetime(when)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None: now = now.replace(tzinfo=timezone.utc)
    delta = due.astimezone(timezone.utc) - now.astimezone(timezone.utc)
    if delta.total_seconds() < 0: return 'OVERDUE'
    if delta.total_seconds() <= soon_hours * 3600: return 'DUE_SOON'
    return 'UPCOMING'


def day_label(value: str) -> str:
    return parse_datetime(value).strftime('%A')
