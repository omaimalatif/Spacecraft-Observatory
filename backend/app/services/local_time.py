# Resolves a ground location's IANA timezone (offline, via timezonefinder's
# bundled boundary data — no network call needed) and reports "right now" in
# both UTC and that location's local time, so visibility results can be
# stamped with a time the person on the ground actually recognizes.

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from timezonefinder import TimezoneFinder

_tf = TimezoneFinder()


def resolve_local_time(lat: float, lon: float) -> dict:
    tz_name = _tf.timezone_at(lat=lat, lng=lon) or "UTC"
    now_utc = datetime.now(timezone.utc)

    try:
        local_dt = now_utc.astimezone(ZoneInfo(tz_name))
    except Exception:
        tz_name = "UTC"
        local_dt = now_utc

    return {
        "timezone": tz_name,
        "utc_iso": now_utc.isoformat(timespec="seconds"),
        "local_iso": local_dt.isoformat(timespec="seconds"),
    }
