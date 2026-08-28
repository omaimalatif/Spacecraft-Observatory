# Forward geocoding — turn a typed place name into lat/lon.
# Uses OpenStreetMap Nominatim: free, no API key, but usage-policy requires a
# descriptive User-Agent and asks clients to cache and not hammer it, so this
# mirrors the same caching pattern used for CelesTrak in services/celestrak.py.
# https://operations.osmfoundation.org/policies/nominatim/

import httpx
from cachetools import TTLCache

_cache = TTLCache(maxsize=512, ttl=3600)  # 1 hour — place names rarely move
BASE = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "ncgsa-orbital-observatory/0.2 (spacecraft observatory location search)"}


async def search_place(query: str, limit: int = 10, country_code: str | None = "pk") -> list[dict]:
    """Return candidate places for a typed query, best match first.
    country_code=None searches worldwide (no country restriction)."""
    query = query.strip()
    if len(query) < 2:
        return []

    key = (query.lower(), limit, country_code)
    if key in _cache:
        return _cache[key]

    params = {"q": query, "format": "jsonv2", "limit": limit, "addressdetails": 1}
    if country_code:
        params["countrycodes"] = country_code
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(BASE, params=params, headers=HEADERS)
        r.raise_for_status()
        raw = r.json()

    results = []
    for item in raw:
        addr = item.get("address") or {}
        results.append({
            "label": item.get("display_name"),
            "lat": float(item["lat"]),
            "lon": float(item["lon"]),
            "type": item.get("type"),
            "country": addr.get("country"),
        })

    _cache[key] = results
    return results
