# CelesTrak SATCAT (Satellite Catalog) client.
# Free, no API key. https://celestrak.org/pub/satcat.csv
#
# Different from celestrak.py's GP feed: SATCAT is CelesTrak's registry of
# every object ever catalogued — on-orbit or decayed — with OBJECT_TYPE
# (PAYLOAD/ROCKET BODY/DEBRIS/UNKNOWN), OPS_STATUS_CODE, OWNER (country/
# entity code), LAUNCH_DATE, DECAY_DATE, and CelesTrak's own computed
# APOGEE/PERIGEE/PERIOD/INCLINATION. This fills in what the GP feed
# structurally can't provide: inactive payloads, rocket bodies, debris
# counts, and country attribution.
#
# NOTE ON THE SOURCE URL: this used to call the query endpoint
# `celestrak.org/satcat/records.php?ONORBIT=1&FORMAT=JSON`. That endpoint
# requires a *primary* search parameter (one of CATNR/INTDES/GROUP/NAME/
# SPECIAL) — ONORBIT is only a filter *on top of* one of those, not a
# standalone query. Calling it with ONORBIT alone gets a 200 OK whose body
# is CelesTrak's own `Invalid query: "..."` message, which silently broke
# every KPI derived from it (debris/rocket_bodies/inactive/countries all
# stayed null forever, with no network error to point at — see the "SATCAT
# temporarily unavailable" notes in space_assets.py). CelesTrak also
# publishes the entire catalog as a single static bulk file with no query
# parameters at all, which is what this module fetches now — simpler,
# and it's the sanctioned way to get "every catalogued object" instead of
# fighting the search API into pretending to be one.
#
# Same caching/stale-serving discipline as celestrak.py, kept as a separate
# module since it's a different endpoint with a different (much
# slower-changing) refresh cadence.

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import time
from pathlib import Path

import httpx
from cachetools import TTLCache

logger = logging.getLogger(__name__)

BASE = "https://celestrak.org/pub/satcat.csv"
USER_AGENT = "NCGSA-Spacecraft-Observatory/0.2 (educational; respects CelesTrak usage policy)"
FRESH_TTL = 21600  # SATCAT changes far more slowly than GP — 6h is generous and polite
REQUEST_TIMEOUT = 60.0  # the full catalog is a large response (tens of thousands of rows)
RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}

# There's only one resource now (the whole bulk file), so the cache just
# needs a single fixed slot rather than one per query-param combination —
# no need for the old tuple-of-(param,value)-pairs cache key at all.
_CACHE_KEY = "satcat_bulk"

_fresh = TTLCache(maxsize=2, ttl=FRESH_TTL)
_stale: dict[str, list] = {}
_locks: dict[str, asyncio.Lock] = {}
_client: httpx.AsyncClient | None = None

CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "satcat"
_DISK_PATH = CACHE_DIR / f"{_CACHE_KEY}.json"


def _load_disk() -> list | None:
    if not _DISK_PATH.exists():
        return None
    try:
        return json.loads(_DISK_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read SATCAT disk cache %s: %s", _DISK_PATH, exc)
        return None


def _save_disk(data) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _DISK_PATH.write_text(json.dumps(data), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not persist SATCAT cache: %s", exc)


def _remember(data) -> None:
    _fresh[_CACHE_KEY] = data
    _stale[_CACHE_KEY] = data


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "text/csv, text/plain, */*"},
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def _request() -> httpx.Response:
    client = await get_client()
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            response = await client.get(BASE)
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
    raise RuntimeError("SATCAT bulk file request failed")


def _to_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _to_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


# Only the columns the rest of the app actually reads (see
# satcat_taxonomy.py and space_assets.py) — matches CelesTrak's published
# CSV field list exactly (celestrak.org/satcat/satcat-format.php), so this
# is a straight rename/typecast, not a guess at their schema.
def _parse_csv(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "NORAD_CAT_ID" not in reader.fieldnames:
        raise RuntimeError(
            f"SATCAT bulk file did not look like the expected CSV (got header: {reader.fieldnames})"
        )
    rows = []
    for row in reader:
        rows.append({
            "OBJECT_NAME": _clean(row.get("OBJECT_NAME")),
            "OBJECT_ID": _clean(row.get("OBJECT_ID")),
            "NORAD_CAT_ID": _to_int(row.get("NORAD_CAT_ID")),
            "OBJECT_TYPE": _clean(row.get("OBJECT_TYPE")),
            "OPS_STATUS_CODE": _clean(row.get("OPS_STATUS_CODE")),
            "OWNER": _clean(row.get("OWNER")),
            "LAUNCH_DATE": _clean(row.get("LAUNCH_DATE")),
            "LAUNCH_SITE": _clean(row.get("LAUNCH_SITE")),
            "DECAY_DATE": _clean(row.get("DECAY_DATE")),
            "PERIOD": _to_float(row.get("PERIOD")),
            "INCLINATION": _to_float(row.get("INCLINATION")),
            "APOGEE": _to_float(row.get("APOGEE")),
            "PERIGEE": _to_float(row.get("PERIGEE")),
            "RCS": _to_float(row.get("RCS")),
            "DATA_STATUS_CODE": _clean(row.get("DATA_STATUS_CODE")),
            "ORBIT_CENTER": _clean(row.get("ORBIT_CENTER")),
            "ORBIT_TYPE": _clean(row.get("ORBIT_TYPE")),
        })
    return rows


async def _fetch_and_store() -> list[dict]:
    response = await _request()
    if response.status_code == 403:
        if _CACHE_KEY in _stale:
            logger.warning("SATCAT bulk file 403 — serving in-memory stale cache")
            return _stale[_CACHE_KEY]
        disk = _load_disk()
        if disk is not None:
            logger.warning("SATCAT bulk file 403 — serving disk stale cache")
            _stale[_CACHE_KEY] = disk
            return disk
        raise RuntimeError("SATCAT bulk file rate-limited (403). Retry later.")

    response.raise_for_status()
    result = _parse_csv(response.text)
    _remember(result)
    _save_disk(result)
    return result


async def _get_full() -> list[dict]:
    if _CACHE_KEY in _fresh:
        return _fresh[_CACHE_KEY]

    lock = _locks.setdefault(_CACHE_KEY, asyncio.Lock())
    async with lock:
        if _CACHE_KEY in _fresh:
            return _fresh[_CACHE_KEY]
        if _CACHE_KEY not in _stale:
            disk = _load_disk()
            if disk is not None:
                _stale[_CACHE_KEY] = disk
        return await _fetch_and_store()


async def fetch_full_catalog() -> list[dict]:
    """Every object ever catalogued, on-orbit AND decayed — for historical population growth."""
    return await _get_full()


async def fetch_onorbit() -> list[dict]:
    """Every currently on-orbit catalogued object — payload, rocket body, or debris.

    The bulk file has no ONORBIT filter (that was only ever a records.php
    query flag), so this is now derived client-side: an object is on-orbit
    if it doesn't have a DECAY_DATE — exactly what ONORBIT=1 meant upstream,
    and it avoids a second network round-trip since the full catalog is
    already cached in-process.
    """
    full = await _get_full()
    return [rec for rec in full if rec.get("DECAY_DATE") is None]


def get_catalog_status(params: dict | None = None) -> str:
    """`params` is accepted for backward compatibility but ignored — there's
    only one underlying resource (the bulk file) now."""
    if _CACHE_KEY in _fresh:
        return "live"
    if _CACHE_KEY in _stale:
        return "cached"
    return "missing"


async def warmup() -> None:
    try:
        full = await fetch_full_catalog()
        logger.info("SATCAT warmup complete (%d catalogued objects)", len(full))
    except Exception as exc:
        logger.warning("SATCAT warmup skipped: %s", exc)


def bootstrap_disk_cache() -> None:
    if not _DISK_PATH.exists():
        return
    data = _load_disk()
    if data is None:
        return
    _stale[_CACHE_KEY] = data
    age = time.time() - _DISK_PATH.stat().st_mtime
    if age < FRESH_TTL:
        _fresh[_CACHE_KEY] = data


# Called at the true end of the module, after every function it depends on
# is already defined — celestrak.py had a real bug from calling its
# equivalent of this mid-file, before a function it transitively needs
# existed yet. Not repeating that here.
bootstrap_disk_cache()