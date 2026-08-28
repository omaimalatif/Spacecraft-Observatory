# Portal 02 — Earth Observation Missions.
# Real sources only: NASA EONET (hazard events), NASA GIBS (imagery tiles),
# NASA FIRMS (active fires, needs a free key), CelesTrak (EO satellite count).
# Anything not backed by a real source is intentionally left out rather than
# filled with placeholder numbers — matching the convention already used in
# Portal 01 (Global Space Assets).

import asyncio
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.services import gibs
from app.services.celestrak import fetch_group_json
from app.services.firms import FirmsNotConfigured, fetch_fires, is_configured

router = APIRouter()

# Tracks the outcome of the last real call to each upstream source, so
# /status can honestly report ONLINE / UNAVAILABLE / NOT CONFIGURED instead
# of guessing.
_service_state: dict[str, dict] = {}


def _record(service: str, ok: bool, detail: str | None = None):
    _service_state[service] = {
        "ok": ok,
        "detail": detail,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/events")
async def events():
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get("https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=50")
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as exc:
        _record("eonet", False, str(exc))
        raise HTTPException(status_code=502, detail=f"Could not reach NASA EONET: {exc}") from exc

    events_list = data.get("events", [])
    _record("eonet", True)
    return {"count": len(events_list), "events": events_list, "source": "NASA EONET v3"}


@router.get("/layers")
def layers():
    """Verified NASA GIBS imagery layers, ready to use as Leaflet XYZ tile sources."""
    return {"layers": gibs.layers_payload(), "source": "NASA GIBS"}


@router.get("/fires")
async def fires(
    bbox: str = Query("world", description="'world' or 'west,south,east,north'"),
    limit: int = Query(2000, le=5000),
):
    """Real active-fire/thermal-anomaly detections — NASA FIRMS (VIIRS NRT, last 24h)."""
    if not is_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "NASA FIRMS is not configured — set FIRMS_MAP_KEY in backend/.env "
                "with a free key from https://firms.modaps.eosdis.nasa.gov/api/map_key/"
            ),
        )
    try:
        data = await fetch_fires(bbox=bbox, limit=limit)
    except FirmsNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        _record("firms", False, str(exc))
        raise HTTPException(status_code=502, detail=f"Could not reach NASA FIRMS: {exc}") from exc
    except RuntimeError as exc:
        _record("firms", False, str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    _record("firms", True)
    high_confidence = [f for f in data if str(f.get("confidence", "")).lower() in ("h", "high") or
                        (str(f.get("confidence", "")).isdigit() and int(f["confidence"]) >= 80)]
    return {
        "count": len(data),
        "high_confidence_count": len(high_confidence),
        "fires": data,
        "window": "last 24 hours",
        "source": "NASA FIRMS (VIIRS_SNPP_NRT)",
    }


@router.get("/satellites")
async def satellites():
    """
    Earth-observation satellite count from CelesTrak's public GP groups that
    map to EO missions (resource + weather). This is an indicative subset of
    CelesTrak's own categorization, not a complete or authoritative EO census
    — a full count would need a mission-registry source (e.g. WMO OSCAR).
    """
    try:
        resource, weather = await asyncio.gather(
            fetch_group_json("resource"),
            fetch_group_json("weather"),
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach CelesTrak: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "earth_resources_satellites": len(resource),
        "weather_satellites": len(weather),
        "total": len(resource) + len(weather),
        "source": "CelesTrak GP catalog (GROUP=resource, GROUP=weather)",
        "note": "Indicative subset of CelesTrak's categorization, not a complete EO satellite census.",
    }


@router.get("/status")
def status():
    """Data-service health for the portal's status panel — never hides a failure."""
    services = [
        {
            "name": "NASA EONET",
            "status": "ONLINE" if _service_state.get("eonet", {}).get("ok") else
                       ("UNAVAILABLE" if "eonet" in _service_state else "NOT YET CHECKED"),
            "url": "https://eonet.gsfc.nasa.gov/",
        },
        {
            "name": "NASA GIBS",
            "status": "ONLINE",  # static tile catalog — the browser fetches tiles directly
            "url": "https://www.earthdata.nasa.gov/gibs",
        },
        {
            "name": "NASA FIRMS",
            "status": (
                "NOT CONFIGURED" if not is_configured() else
                ("ONLINE" if _service_state.get("firms", {}).get("ok") else
                 ("UNAVAILABLE" if "firms" in _service_state else "NOT YET CHECKED"))
            ),
            "url": "https://firms.modaps.eosdis.nasa.gov/",
        },
        {"name": "ESA / Copernicus", "status": "NOT CONNECTED", "url": "https://dataspace.copernicus.eu/"},
        {"name": "USGS Landsat", "status": "NOT CONNECTED", "url": "https://www.usgs.gov/landsat-missions"},
        {"name": "NOAA", "status": "NOT CONNECTED", "url": "https://www.noaa.gov/"},
    ]
    return {"services": services, "checked_at": datetime.now(timezone.utc).isoformat()}
