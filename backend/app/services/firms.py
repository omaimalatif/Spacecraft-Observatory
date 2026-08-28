# NASA FIRMS (Fire Information for Resource Management System) — near-real-time
# active fire/thermal-anomaly detections from MODIS and VIIRS.
# https://firms.modaps.eosdis.nasa.gov/api/
#
# Requires a free MAP_KEY (https://firms.modaps.eosdis.nasa.gov/api/map_key/).
# Without one, this module reports itself as "not configured" rather than
# failing silently or fabricating fire data.

import csv
import io
import os

import httpx
from cachetools import TTLCache

BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
SOURCE = "VIIRS_SNPP_NRT"  # near-real-time, 375m resolution, good global default
DAY_RANGE = 1

# FIRMS' own guidance: don't hammer it. 15 min is well inside their published
# rate limit and matches how often a new NRT pass is actually available.
_cache = TTLCache(maxsize=8, ttl=900)


class FirmsNotConfigured(Exception):
    pass


def is_configured() -> bool:
    return bool(os.environ.get("FIRMS_MAP_KEY"))


async def fetch_fires(bbox: str = "world", limit: int = 2000) -> list[dict]:
    """
    Real active-fire detections for a bounding box ('world' or
    'west,south,east,north'). An empty list is a legitimate "no fires
    detected" result from FIRMS itself, distinct from a configuration or
    network failure, which raises instead.
    """
    map_key = os.environ.get("FIRMS_MAP_KEY")
    if not map_key:
        raise FirmsNotConfigured(
            "FIRMS_MAP_KEY is not set. Get a free key at "
            "https://firms.modaps.eosdis.nasa.gov/api/map_key/ and add it to backend/.env"
        )

    cache_key = (bbox, SOURCE, DAY_RANGE)
    if cache_key in _cache:
        return _cache[cache_key][:limit]

    url = f"{BASE}/{map_key}/{SOURCE}/{bbox}/{DAY_RANGE}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url)
        r.raise_for_status()
        text = r.text

    # FIRMS returns a short plain-text error body (not CSV) for a bad key,
    # exhausted transaction quota, etc. — catch that before trying to parse.
    if not text.strip() or "latitude" not in text.splitlines()[0].lower():
        raise RuntimeError(f"FIRMS did not return fire data: {text[:200]}")

    reader = csv.DictReader(io.StringIO(text))
    fires = []
    for row in reader:
        try:
            fires.append({
                "lat": float(row["latitude"]),
                "lon": float(row["longitude"]),
                "acq_date": row.get("acq_date"),
                "acq_time": row.get("acq_time"),
                "satellite": row.get("satellite"),
                "instrument": row.get("instrument"),
                "confidence": row.get("confidence"),
                "frp": float(row["frp"]) if row.get("frp") not in (None, "") else None,
                "daynight": row.get("daynight"),
            })
        except (KeyError, ValueError):
            continue  # skip malformed rows rather than fail the whole batch

    _cache[cache_key] = fires
    return fires[:limit]
