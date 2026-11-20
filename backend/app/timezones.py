"""Per-user timezone validation and local-calendar-day boundaries."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_TIMEZONE = "UTC"


def validated_timezone(name: str | None) -> ZoneInfo:
    """Resolve an IANA timezone; reject abbreviations and unknown identifiers."""
    if not name or len(name) > 64:
        raise ValueError("Bitte eine gültige IANA-Zeitzone angeben.")
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        raise ValueError(
            "Diese Zeitzone ist auf dem Server nicht verfügbar. "
            "Bitte die Backend-Abhängigkeiten einschließlich tzdata installieren."
        ) from None
    except ValueError:
        raise ValueError("Bitte eine gültige IANA-Zeitzone angeben.") from None


def normalize_utc(value: datetime) -> datetime:
    """Interpret naive legacy inputs as UTC and convert aware inputs to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def local_today(timezone_name: str | None) -> date:
    return datetime.now(validated_timezone(timezone_name or DEFAULT_TIMEZONE)).date()


def local_day_bounds(day: date, timezone_name: str | None) -> tuple[datetime, datetime]:
    """Return UTC-aware [start, end) bounds for a local calendar day.

    Constructing each local midnight independently is essential: a DST day
    can be 23 or 25 hours long.
    """
    zone = validated_timezone(timezone_name or DEFAULT_TIMEZONE)
    start_local = datetime.combine(day, time.min, tzinfo=zone)
    next_local = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    return start_local.astimezone(timezone.utc), next_local.astimezone(timezone.utc)
