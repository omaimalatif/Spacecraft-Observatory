# CelesTrak SATCAT (Satellite Catalog) client.
# Free, no API key. https://celestrak.org/satcat/records.php
#
# Different from celestrak.py's GP feed: SATCAT is CelesTrak's registry of
# every object ever catalogued — on-orbit or decayed — with OBJECT_TYPE
# (PAYLOAD/ROCKET BODY/DEBRIS/UNKNOWN), OPS_STATUS_CODE, OWNER (country/
# entity code), LAUNCH_DATE, DECAY_DATE, and CelesTrak's own computed
# APOGEE/PERIGEE/PERIOD/INCLINATION. This fills in what the GP feed
# structurally can't provide: inactive payloads, rocket bodies, debris
# counts, and country attribution. Same caching/stale-serving discipline as
# celestrak.py, kept as a separate module since it's a different endpoint
# with a different (much slower-changing) refresh cadence.

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

import httpx
from cachetools import TTLCache

logger = logging.getLogger(__name__)

BASE = "https://celestrak.org/satcat/records.php"
USER_AGENT = "NCGSA-Spacecraft-Observatory/0.2 (educational; respects CelesTrak usage policy)"
FRESH_TTL = 21600  # SATCAT changes far more slowly than GP — 6h is generous and polite
REQUEST_TIMEOUT = 60.0  # the full on-orbit catalog is a large response
RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}

_fresh = TTLCache(maxsize=8, ttl=FRESH_TTL)
_stale: dict[tuple, list] = {}
_locks: dict[tuple, asyncio.Lock] = {}
_client: httpx.AsyncClient | None = None

CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "satcat"


def _cache_key(params: dict) -> tuple:
    normalized = {str(k).upper(): str(v).upper() for k, v in params.items()}
    normalized["FORMAT"] = "JSON"
    return tuple(sorted(normalized.items()))


def _disk_path(key: tuple) -> Path:
    safe = "_".join(f"{k}-{v}" for k, v in key).replace("/", "_")
    return CACHE_DIR / f"{safe}.json"


def _load_disk(key: tuple):
    path = _disk_path(key)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read SATCAT disk cache %s: %s", path, exc)
        return None


def _save_disk(key: tuple, data) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _disk_path(key).write_text(json.dumps(data), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not persist SATCAT cache: %s", exc)


def _remember(key: tuple, data) -> None:
    _fresh[key] = data
    _stale[key] = data


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"},
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
            response = await client.get(BASE, params={**params, "FORMAT": "JSON"})
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
    raise RuntimeError(f"SATCAT request failed for {params}")


def _parse_response(response: httpx.Response) -> list[dict]:
    content_type = response.headers.get("content-type", "")
    if "json" not in content_type.lower():
        raise RuntimeError(f"SATCAT returned non-JSON data: {response.status_code} {response.text[:180]}")
    result = response.json()
    if not isinstance(result, list):
        raise RuntimeError("SATCAT returned an unexpected JSON response")
    return result


async def _fetch_and_store(key: tuple, params: dict) -> list[dict]:
    response = await _request(params)
    if response.status_code == 403:
        if key in _stale:
            logger.warning("SATCAT 403 for %s — serving in-memory stale cache", params)
            return _stale[key]
        disk = _load_disk(key)
        if disk is not None:
            logger.warning("SATCAT 403 for %s — serving disk stale cache", params)
            _stale[key] = disk
            return disk
        raise RuntimeError(f"SATCAT rate-limited for {params}. Retry later.")

    response.raise_for_status()
    result = _parse_response(response)
    _remember(key, result)
    _save_disk(key, result)
    return result


async def _get(params: dict) -> list[dict]:
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
        return await _fetch_and_store(key, params)


async def fetch_onorbit() -> list[dict]:
    """Every currently on-orbit catalogued object — payload, rocket body, or debris."""
    return await _get({"ONORBIT": 1})


async def fetch_full_catalog() -> list[dict]:
    """Every object ever catalogued, on-orbit AND decayed — for historical population growth."""
    return await _get({})


def get_catalog_status(params: dict) -> str:
    key = _cache_key(params)
    if key in _fresh:
        return "live"
    if key in _stale:
        return "cached"
    return "missing"


async def warmup() -> None:
    try:
        await fetch_onorbit()
        logger.info("SATCAT warmup complete (ONORBIT=1)")
    except Exception as exc:
        logger.warning("SATCAT warmup skipped: %s", exc)


def bootstrap_disk_cache() -> None:
    if not CACHE_DIR.exists():
        return
    for path in CACHE_DIR.glob("*.json"):
        parts = []
        for segment in path.stem.split("_"):
            if "-" not in segment:
                continue
            k, v = segment.split("-", 1)
            parts.append((k, v))
        if not parts:
            continue
        key = tuple(sorted(parts))
        data = _load_disk(key)
        if data is None:
            continue
        _stale[key] = data
        age = time.time() - path.stat().st_mtime
        if age < FRESH_TTL:
            _fresh[key] = data


# Called at the true end of the module, after every function it depends on
# is already defined — celestrak.py had a real bug from calling its
# equivalent of this mid-file, before a function it transitively needs
# existed yet. Not repeating that here.
bootstrap_disk_cache()
