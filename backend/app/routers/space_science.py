# Portal 06 — Space Science & Exploration Missions.
# Real sources only: NASA/JPL Horizons (planet + spacecraft positions,
# EPHEMERIS-DERIVED — computed from tracked orbital solutions, not live
# telemetry) and NASA NeoWs (near-Earth object close approaches).
#
# Route prefix follows this project's existing convention (/api/<portal>,
# no /v1/ versioning segment) to match every other portal router rather than
# introduce a one-off URL shape.

import asyncio
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.services import jpl_horizons, nasa_neows

router = APIRouter()

_service_state: dict[str, dict] = {}


def _record(service: str, ok: bool, detail: str | None = None):
    _service_state[service] = {"ok": ok, "detail": detail, "checked_at": datetime.now(timezone.utc).isoformat()}


# Curated real missions. `launch_date`/`agency`/`target` are static reference
# facts (do not change), clearly separate from `position`, which is
# EPHEMERIS-DERIVED and fetched fresh each request (subject to caching).
# Spacecraft IDs are resolved by name via Horizons' own Lookup API rather
# than hardcoded, so a wrong guessed ID can never masquerade as real data.
SPACECRAFT_CATALOG = [
    {"key": "voyager-1", "name": "Voyager 1", "agency": "NASA / JPL", "launch_date": "1977-09-05",
     "target": "Interstellar space", "status": "Operating (interstellar mission)"},
    {"key": "voyager-2", "name": "Voyager 2", "agency": "NASA / JPL", "launch_date": "1977-08-20",
     "target": "Interstellar space", "status": "Operating (interstellar mission)"},
    {"key": "new-horizons", "name": "New Horizons", "agency": "NASA / APL", "launch_date": "2006-01-19",
     "target": "Kuiper Belt", "status": "Operating (extended mission)"},
    {"key": "parker-solar-probe", "name": "Parker Solar Probe", "agency": "NASA / APL", "launch_date": "2018-08-12",
     "target": "Sun", "status": "Operating"},
]


async def _spacecraft_with_position(entry: dict) -> dict:
    try:
        spkid = await jpl_horizons.resolve_spkid(entry["name"])
    except httpx.HTTPError as exc:
        return {**entry, "position": None, "position_error": f"Could not reach JPL Horizons: {exc}"}

    if not spkid:
        return {**entry, "position": None, "position_error": "Could not resolve a Horizons SPK-ID for this mission"}
    try:
        vector = await jpl_horizons.get_state_vector(spkid)
    except (httpx.HTTPError, jpl_horizons.HorizonsError) as exc:
        return {**entry, "position": None, "position_error": str(exc)}
    return {**entry, "spkid": spkid, "position": vector}


@router.get("/solar-system")
async def solar_system():
    """Sun + 8 planets, heliocentric-frame positions computed by JPL Horizons right now."""
    try:
        results = await asyncio.gather(*(
            jpl_horizons.get_state_vector(cmd) for cmd in jpl_horizons.MAJOR_BODIES.values()
        ))
    except httpx.HTTPError as exc:
        _record("horizons", False, str(exc))
        raise HTTPException(status_code=502, detail=f"Could not reach JPL Horizons: {exc}") from exc
    except jpl_horizons.HorizonsError as exc:
        _record("horizons", False, str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    _record("horizons", True)
    bodies = [
        {"name": name.capitalize(), "command": cmd, **vector}
        for (name, cmd), vector in zip(jpl_horizons.MAJOR_BODIES.items(), results)
    ]
    return {"bodies": bodies, "label": "EPHEMERIS-DERIVED", "source": "NASA/JPL Horizons"}


@router.get("/spacecraft")
async def spacecraft():
    """Curated real deep-space missions with EPHEMERIS-DERIVED current positions."""
    results = await asyncio.gather(*(_spacecraft_with_position(m) for m in SPACECRAFT_CATALOG))
    ok_count = sum(1 for r in results if r.get("position"))
    _record("horizons", ok_count > 0)
    return {
        "missions": list(results),
        "resolved_count": ok_count,
        "total_count": len(SPACECRAFT_CATALOG),
        "label": "Reference facts are static; positions are EPHEMERIS-DERIVED from NASA/JPL Horizons",
        "source": "NASA/JPL Horizons",
    }


@router.get("/neo")
async def neo(days: int = Query(7, ge=1, le=7)):
    """Real near-Earth object close approaches — NASA NeoWs, next `days` days."""
    try:
        data = await nasa_neows.fetch_neo_feed(days=days)
    except httpx.HTTPError as exc:
        _record("neows", False, str(exc))
        raise HTTPException(status_code=502, detail=f"Could not reach NASA NeoWs: {exc}") from exc

    _record("neows", True)
    hazardous = [n for n in data if n["is_potentially_hazardous"]]
    return {
        "count": len(data),
        "hazardous_count": len(hazardous),
        "objects": data,
        "window_days": days,
        "using_demo_key": nasa_neows.using_demo_key(),
        "hazard_label": "NASA's own 'potentially hazardous asteroid' classification — not an NCGSA-derived risk score",
        "source": "NASA NeoWs",
    }


@router.get("/status")
def status():
    services = [
        {
            "name": "NASA/JPL Horizons",
            "status": "ONLINE" if _service_state.get("horizons", {}).get("ok") else
                       ("UNAVAILABLE" if "horizons" in _service_state else "NOT YET CHECKED"),
            "url": "https://ssd.jpl.nasa.gov/horizons/",
        },
        {
            "name": "NASA NeoWs" + (" (DEMO_KEY)" if nasa_neows.using_demo_key() else ""),
            "status": "ONLINE" if _service_state.get("neows", {}).get("ok") else
                       ("UNAVAILABLE" if "neows" in _service_state else "NOT YET CHECKED"),
            "url": "https://api.nasa.gov/",
        },
        {"name": "NASA Exoplanet Archive", "status": "NOT CONNECTED", "url": "https://exoplanetarchive.ipac.caltech.edu/"},
        {"name": "HEASARC", "status": "NOT CONNECTED", "url": "https://heasarc.gsfc.nasa.gov/"},
        {"name": "Minor Planet Center", "status": "NOT CONNECTED", "url": "https://www.minorplanetcenter.net/"},
        {"name": "NOAA Space Weather Prediction Center", "status": "NOT CONNECTED", "url": "https://www.swpc.noaa.gov/"},
    ]
    return {"services": services, "checked_at": datetime.now(timezone.utc).isoformat()}
