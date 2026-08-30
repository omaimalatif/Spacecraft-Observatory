# CelesTrak GP (General Perturbations) catalog client.
# Free, no API key. https://celestrak.org/NORAD/elements/gp.php
#
# CelesTrak updates GP data every ~2 hours and enforces a one-download-per-cycle
# policy on large groups (e.g. active, starlink). This module deduplicates
# in-flight requests, caches for 2 hours, persists the last good payload to disk,
# and serves stale data when upstream returns 403 instead of hammering the API.

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

import httpx
from cachetools import TTLCache

from app.services.satcat_taxonomy import classify_satellite_type

logger = logging.getLogger(__name__)

BASE = "https://celestrak.org/NORAD/elements/gp.php"
USER_AGENT = "NCGSA-Spacecraft-Observatory/0.2 (educational; respects CelesTrak usage policy)"
FRESH_TTL = 7200  # match CelesTrak GP refresh cadence (~2 hours)
REQUEST_TIMEOUT = 45.0
RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}

_fresh = TTLCache(maxsize=64, ttl=FRESH_TTL)
_stale: dict[tuple, list | str] = {}
_locks: dict[tuple, asyncio.Lock] = {}
_client: httpx.AsyncClient | None = None
_search_index: list[tuple[str, str, str, dict]] | None = None

CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "celestrak"


def _normalize_params(params: dict) -> dict:
    normalized = dict(params)
    if "GROUP" in normalized:
        normalized["GROUP"] = str(normalized["GROUP"]).upper()
    if "FORMAT" in normalized:
        normalized["FORMAT"] = str(normalized["FORMAT"]).upper()
    return normalized


def _cache_key(params: dict) -> tuple:
    return tuple(sorted(_normalize_params(params).items()))


def _disk_path(key: tuple) -> Path:
    safe = "_".join(f"{k}-{v}" for k, v in key).replace("/", "_")
    return CACHE_DIR / f"{safe}.json"


def _hydrate_from_disk(key: tuple) -> bool:
    path = _disk_path(key)
    if not path.exists():
        return False
    data = _load_disk(key)
    if data is None:
        return False
    _stale[key] = data
    age = time.time() - path.stat().st_mtime
    if age < FRESH_TTL:
        _fresh[key] = data
    if isinstance(data, list) and key == _cache_key({"GROUP": "active", "FORMAT": "json"}):
        _rebuild_search_index(data)
    return True


def bootstrap_disk_cache() -> None:
    if not CACHE_DIR.exists():
        return
    for path in CACHE_DIR.glob("*.json"):
        parts = []
        for segment in path.stem.split("_"):
            if "-" not in segment:
                continue
            key, value = segment.split("-", 1)
            parts.append((key, value))
        if parts:
            _hydrate_from_disk(tuple(sorted(parts)))


def _load_disk(key: tuple):
    path = _disk_path(key)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read CelesTrak disk cache %s: %s", path, exc)
        return None


def _save_disk(key: tuple, data) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _disk_path(key).write_text(json.dumps(data), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not persist CelesTrak cache: %s", exc)


def _remember(key: tuple, data) -> None:
    _fresh[key] = data
    _stale[key] = data
    if isinstance(data, list) and key == _cache_key({"GROUP": "active", "FORMAT": "json"}):
        _rebuild_search_index(data)


def _rebuild_search_index(objects: list[dict]) -> None:
    global _search_index
    _search_index = [
        (
            str(item.get("OBJECT_NAME", "")).lower(),
            str(item.get("NORAD_CAT_ID", "")).lower(),
            str(item.get("OBJECT_ID", "")).lower(),
            item,
        )
        for item in objects
    ]


def _restore_search_index_from_disk() -> None:
    key = _cache_key({"GROUP": "active", "FORMAT": "json"})
    if key in _stale and isinstance(_stale[key], list):
        _rebuild_search_index(_stale[key])
        return
    disk = _load_disk(key)
    if isinstance(disk, list):
        _stale[key] = disk
        _rebuild_search_index(disk)


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/plain, */*",
            },
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def _request(params: dict) -> httpx.Response:
    client = await get_client()
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            response = await client.get(BASE, params=_normalize_params(params))
        except httpx.TransportError as exc:
            last_exc = exc
            if attempt < 2:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            raise
        if response.status_code in RETRYABLE_STATUSES and attempt < 2:
            await asyncio.sleep(1.5 * (attempt + 1))
            continue
        return response
    if last_exc:
        raise last_exc
    raise RuntimeError(f"CelesTrak request failed for {params}")


def _parse_response(params: dict, response: httpx.Response):
    if params.get("FORMAT", "JSON").upper() == "JSON":
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type.lower():
            raise RuntimeError(
                f"CelesTrak returned non-JSON data for {params}: "
                f"{response.status_code} {response.text[:180]}"
            )
        result = response.json()
        if not isinstance(result, list):
            raise RuntimeError(f"CelesTrak returned an unexpected JSON response for {params}")
        return result
    return response.text


async def _fetch_and_store(key: tuple, params: dict):
    try:
        response = await _request(params)
    except httpx.HTTPError:
        if key in _stale:
            logger.warning("CelesTrak request failed for %s — serving stale cache", params)
            return _stale[key]
        raise
    if response.status_code == 403:
        if key in _stale:
            logger.warning("CelesTrak 403 for %s — serving in-memory stale cache", params)
            return _stale[key]
        disk = _load_disk(key)
        if disk is not None:
            logger.warning("CelesTrak 403 for %s — serving disk stale cache", params)
            _stale[key] = disk
            if isinstance(disk, list) and key == _cache_key({"GROUP": "active", "FORMAT": "json"}):
                _rebuild_search_index(disk)
            return disk
        request_desc = f"GROUP={params['GROUP']}" if "GROUP" in params else f"CATNR={params.get('CATNR')}"
        raise RuntimeError(
            f"CelesTrak rate-limited {request_desc} "
            "(one download per ~2-hour GP refresh). Retry after the next catalog update."
        )

    response.raise_for_status()
    result = _parse_response(params, response)
    _remember(key, result)
    _save_disk(key, result)
    return result


async def _get(params: dict):
    key = _cache_key(params)
    if key in _fresh:
        return _fresh[key]

    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        if key in _fresh:
            return _fresh[key]

        if key not in _stale:
            disk = _load_disk(key)
            if disk is not None:
                _stale[key] = disk
                if isinstance(disk, list) and key == _cache_key({"GROUP": "active", "FORMAT": "json"}):
                    _rebuild_search_index(disk)

        return await _fetch_and_store(key, params)


async def fetch_group_json(group: str) -> list[dict]:
    """OMM-format records for a CelesTrak group — e.g. active, stations, gnss, starlink."""
    return await _get({"GROUP": group, "FORMAT": "json"})


async def fetch_group_tle(group: str) -> list[dict]:
    """[{name, line1, line2}, ...] triplets for a CelesTrak group, ready for SGP4 propagation."""
    text = await _get({"GROUP": group, "FORMAT": "tle"})
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    sats = []
    for i in range(0, len(lines) - 2, 3):
        sats.append({"name": lines[i].strip(), "line1": lines[i + 1], "line2": lines[i + 2]})
    return sats


async def fetch_object_tle(norad_id: int) -> dict | None:
    """Single-object TLE by NORAD catalog number — goes through the same
    cache/retry/stale-serving path as everything else, just keyed on CATNR
    instead of GROUP."""
    text = await _get({"CATNR": norad_id, "FORMAT": "tle"})
    if not isinstance(text, str):
        return None
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) < 3:
        return None
    return {"name": lines[0].strip(), "line1": lines[1], "line2": lines[2]}


def shape_object_minimal(item: dict) -> dict:
    """Trim a full OMM record to the fields the Global Assets UI actually renders."""
    fields = (
        "OBJECT_NAME",
        "NORAD_CAT_ID",
        "OBJECT_ID",
        "EPOCH",
        "MEAN_MOTION",
        "INCLINATION",
        "ECCENTRICITY",
    )
    shaped = {field: item.get(field) for field in fields}
    # This function only ever sees records from GROUP=active / GROUP=stations
    # (search() and the globe both source from there), so "active" is a fact
    # about the source list, not an inference. Type is still best-effort —
    # see satcat_taxonomy.classify_satellite_type.
    shaped["OPS_STATUS"] = "active"
    shaped["SATELLITE_TYPE"] = classify_satellite_type(item.get("OBJECT_NAME"))
    return shaped


def search_active_catalog(query: str, limit: int = 25) -> list[dict]:
    """Search the cached active catalog without re-fetching CelesTrak."""
    if _search_index is None:
        _restore_search_index_from_disk()
    if not _search_index:
        return []

    needle = query.strip().lower()
    if not needle:
        return []

    matches: list[dict] = []
    for name, norad, cospar, item in _search_index:
        if needle in name or needle == norad or needle in cospar:
            matches.append(item)
            if len(matches) >= limit:
                break
    return matches


def get_catalog_status(group: str) -> str:
    key = _cache_key({"GROUP": group, "FORMAT": "json"})
    if key in _fresh:
        return "live"
    if key in _stale:
        return "cached"
    return "missing"


async def warmup_catalog(
    groups: tuple[str, ...] = (
        "last-30-days", "active",
        # Every group a portal in this app actually fetches. Warming all of
        # them once at startup means the first click into any portal reads
        # from cache instead of cold-fetching — and fetching them here,
        # sequentially with a pause between each, is also what keeps a dev
        # server restart from re-hammering CelesTrak across 15 groups at
        # once and tripping its per-cycle rate limit.
        "gnss", "weather", "stations", "science", "cubesat", "resource",
        "intelsat", "ses", "eutelsat", "telesat", "iridium-NEXT", "orbcomm", "globalstar", "amateur",
    ),
) -> None:
    """Prefetch every group this app uses once at startup (sequential, with a
    short pause between requests, to respect CelesTrak's rate limits)."""
    for i, group in enumerate(groups):
        if i > 0:
            await asyncio.sleep(0.35)
        try:
            await fetch_group_json(group)
            logger.info("CelesTrak warmup complete for GROUP=%s", group)
        except Exception as exc:
            logger.warning("CelesTrak warmup skipped for GROUP=%s: %s", group, exc)


# Run at true end-of-module so every function it depends on (including
# _rebuild_search_index, defined further up but still after this used to
# sit) is already bound in the module namespace. This used to be called
# right after its own definition, ~40 lines above _rebuild_search_index —
# harmless when there was no disk cache yet to hydrate, but a NameError as
# soon as a real .cache/celestrak/*.json file exists for it to load.
bootstrap_disk_cache()
