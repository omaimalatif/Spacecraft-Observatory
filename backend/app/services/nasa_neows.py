# NASA NeoWs (Near Earth Object Web Service) — real close-approach data for
# asteroids/comets. https://api.nasa.gov/ (see "Asteroids - NeoWs")
#
# Works out of the box with NASA's public DEMO_KEY (shared, low rate limit:
# ~30 requests/hour, 50/day) so this feature isn't blocked before you get
# your own key. Set NASA_API_KEY in backend/.env for a much higher personal
# limit (1000/hour) — same pattern as FIRMS_MAP_KEY.
#
# Hazard classification is passed through verbatim as NASA's own
# `is_potentially_hazardous_asteroid` flag — this module does not compute or
# invent any risk score of its own.

import os
from datetime import date, timedelta

import httpx
from cachetools import TTLCache

BASE = "https://api.nasa.gov/neo/rest/v1/feed"
_cache = TTLCache(maxsize=8, ttl=1800)  # 30 min — NeoWs feed data doesn't change that fast


def api_key() -> str:
    return os.environ.get("NASA_API_KEY") or "DEMO_KEY"


def using_demo_key() -> bool:
    return not os.environ.get("NASA_API_KEY")


async def fetch_neo_feed(days: int = 7) -> list[dict]:
    """
    Real near-Earth object close approaches from today through `days` ahead
    (NeoWs caps a single request at 7 days). Empty list is a legitimate "none
    today" result, distinct from a request failure which raises.
    """
    days = min(days, 7)
    start = date.today()
    end = start + timedelta(days=days)
    cache_key = (start.isoformat(), end.isoformat())
    if cache_key in _cache:
        return _cache[cache_key]

    params = {"start_date": start.isoformat(), "end_date": end.isoformat(), "api_key": api_key()}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(BASE, params=params)
        r.raise_for_status()
        data = r.json()

    by_date = data.get("near_earth_objects", {})
    neos = []
    for day, objects in by_date.items():
        for obj in objects:
            approach = (obj.get("close_approach_data") or [{}])[0]
            diameter = (obj.get("estimated_diameter") or {}).get("kilometers") or {}
            neos.append({
                "id": obj.get("id"),
                "name": obj.get("name"),
                "nasa_jpl_url": obj.get("nasa_jpl_url"),
                "is_potentially_hazardous": obj.get("is_potentially_hazardous_asteroid"),
                "estimated_diameter_km_min": diameter.get("estimated_diameter_min"),
                "estimated_diameter_km_max": diameter.get("estimated_diameter_max"),
                "close_approach_date": approach.get("close_approach_date_full") or approach.get("close_approach_date") or day,
                "miss_distance_km": (approach.get("miss_distance") or {}).get("kilometers"),
                "relative_velocity_kph": (approach.get("relative_velocity") or {}).get("kilometers_per_hour"),
                "orbiting_body": approach.get("orbiting_body"),
            })

    neos.sort(key=lambda n: n["close_approach_date"] or "")
    _cache[cache_key] = neos
    return neos
