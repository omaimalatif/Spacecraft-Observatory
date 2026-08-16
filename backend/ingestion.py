"""
Ingestion layer. The frontend never talks to CelesTrak or Space-Track
directly -- everything goes through here, gets normalized, and is
cached so we aren't hammering upstream providers on every page load.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from models import SpaceObject
from normalize import normalize_batch

logger = logging.getLogger("ingestion")

CELESTRAK_BASE = "https://celestrak.org/NORAD/elements/gp.php"

# CelesTrak-documented group identifiers we support out of the box.
# Not exhaustive -- check https://celestrak.org/NORAD/elements/ for the
# current full list before assuming a group name is valid.
SUPPORTED_GROUPS = {
    "STATIONS": "Space stations",
    "ACTIVE": "All active satellites",
    "GNSS": "All GNSS/navigation satellites",
    "GPS-OPS": "GPS operational",
    "WEATHER": "Weather satellites",
    "EARTH-RESOURCES": "Earth resources / remote sensing",
    "CUBESAT": "CubeSats",
    "SCIENCE": "Scientific satellites",
    "GEO": "Geostationary satellites",
}

# Minimum seconds between re-fetching the same group from CelesTrak.
# CelesTrak's own guidance is to not poll more than a few times a day
# per group -- GP data does not change that fast.
MIN_REFRESH_INTERVAL_S = int(os.environ.get("CELESTRAK_MIN_REFRESH_S", 6 * 3600))


@dataclass
class CacheEntry:
    objects: list[SpaceObject]
    dropped: int
    fetched_at: float = field(default_factory=time.time)


class CelesTrakClient:
    """Thin client + in-memory cache. Swap the cache for Redis/DB-backed
    storage for a real multi-instance deployment -- this is enough for
    a single-process reference implementation."""

    def __init__(self, timeout_s: float = 20.0):
        self._client = httpx.Client(timeout=timeout_s, headers={
            "User-Agent": "global-space-assets-dashboard/1.0 (contact: ops@example.com)"
        })
        self._cache: dict[str, CacheEntry] = {}

    def _fetch_raw(self, group: str) -> list[dict[str, Any]]:
        if group not in SUPPORTED_GROUPS:
            raise ValueError(
                f"Unsupported group '{group}'. Supported: {sorted(SUPPORTED_GROUPS)}. "
                "Verify against https://celestrak.org/NORAD/elements/ before adding new ones."
            )
        resp = self._client.get(CELESTRAK_BASE, params={"GROUP": group, "FORMAT": "JSON"})
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            raise ValueError(f"Unexpected CelesTrak response shape for group={group}: {type(data)}")
        return data

    def get_group(self, group: str, force_refresh: bool = False) -> CacheEntry:
        cached = self._cache.get(group)
        if cached and not force_refresh and (time.time() - cached.fetched_at) < MIN_REFRESH_INTERVAL_S:
            return cached

        try:
            raw_records = self._fetch_raw(group)
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("CelesTrak fetch failed for group=%s: %s", group, exc)
            if cached:
                # Serve stale data rather than nothing -- freshness status
                # in the API response will reflect that it's stale.
                return cached
            raise

        objects, dropped = normalize_batch(raw_records, provider="CelesTrak")
        entry = CacheEntry(objects=objects, dropped=dropped)
        self._cache[group] = entry
        logger.info("Ingested %d objects (%d dropped) for group=%s", len(objects), dropped, group)
        return entry

    def close(self) -> None:
        self._client.close()


class SpaceTrackClient:
    """Secondary/verification source. Credentials are read from
    environment variables ONLY and never exposed to the frontend --
    this class is only ever instantiated server-side.

    This is a minimal reference implementation of the Space-Track
    auth flow (POST to ajaxauth/login, then query authenticated
    endpoints using the same session). Space-Track throttles
    aggressively -- do not call this per-frontend-request; use it for
    periodic batch verification/enrichment jobs only.
    """

    LOGIN_URL = "https://www.space-track.org/ajaxauth/login"
    QUERY_BASE = "https://www.space-track.org/basicspacedata/query"

    def __init__(self):
        self.username = os.environ.get("SPACE_TRACK_USERNAME")
        self.password = os.environ.get("SPACE_TRACK_PASSWORD")
        self._client: httpx.Client | None = None

    @property
    def configured(self) -> bool:
        return bool(self.username and self.password)

    def _ensure_session(self) -> httpx.Client:
        if not self.configured:
            raise RuntimeError(
                "Space-Track credentials not configured. Set SPACE_TRACK_USERNAME "
                "and SPACE_TRACK_PASSWORD as server-side environment variables."
            )
        if self._client is None:
            client = httpx.Client(timeout=30.0)
            resp = client.post(self.LOGIN_URL, data={
                "identity": self.username,
                "password": self.password,
            })
            resp.raise_for_status()
            self._client = client
        return self._client

    def query_gp(self, norad_cat_ids: list[str]) -> list[dict[str, Any]]:
        """Fetch GP data for a specific set of catalog IDs, for
        cross-checking against CelesTrak. Use sparingly and cache
        results -- respect Space-Track's rate limits."""
        client = self._ensure_session()
        ids = ",".join(norad_cat_ids)
        url = f"{self.QUERY_BASE}/class/gp/NORAD_CAT_ID/{ids}/format/json"
        resp = client.get(url)
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
