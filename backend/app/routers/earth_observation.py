# Portal 02 — Earth Observation Satellites.
# Purpose: which satellites are watching Earth for fires, storms, floods and
# other hazards, with real live orbital positions — not the hazard events
# themselves (that's a different problem and a different data need; the
# fire/event/imagery endpoints below are kept for API compatibility but the
# portal UI no longer uses them).
# Real sources only: CelesTrak GP (GROUP=resource, GROUP=weather) for the
# satellites themselves, CelesTrak SATCAT for real active/inactive status.
# Anything not backed by a real source is intentionally left out rather than
# filled with placeholder numbers — matching the convention used in
# Portal 01 (Global Space Assets).

import asyncio
from datetime import datetime, timezone

import httpx
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException, Query

from app.services import gibs
from app.services.celestrak import fetch_group_json, fetch_group_tle
from app.services.eo_taxonomy import HAZARD_FOCUS_LABELS, classify_hazard_focus
from app.services.firms import FirmsNotConfigured, fetch_fires, is_configured
from app.services.orbital import classify_regime, propagate_subpoints
from app.services.satcat import fetch_onorbit as fetch_satcat_onorbit
from app.services.satcat_taxonomy import classify_ops_status

router = APIRouter()

EO_SOURCE = "CelesTrak GP (GROUP=resource, GROUP=weather), SGP4-propagated"
EO_GROUPS = ["resource", "weather"]
_eo_globe_cache = TTLCache(maxsize=2, ttl=300)

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


def _cospar_id_from_tle_line1(line1: str) -> str | None:
    """International designator lives in TLE line 1, columns 10–17
    (e.g. '98067A  ' -> '1998-067A'). Real data parsed from the TLE
    already being propagated — not a separate lookup."""
    try:
        raw = line1[9:17].strip()
        if not raw or len(raw) < 5:
            return None
        yy = int(raw[:2])
        year = 1900 + yy if yy >= 57 else 2000 + yy
        rest = raw[2:].strip()
        return f"{year}-{rest}" if rest else None
    except (ValueError, IndexError):
        return None


async def _fetch_group_tle_safe(group: str) -> list[dict]:
    try:
        return await fetch_group_tle(group)
    except Exception:
        return []  # this one group is unavailable right now — the rest still renders


async def _eo_globe_objects() -> dict:
    """Every satellite in CelesTrak's resource + weather GP groups, real
    SGP4-propagated positions, classified by which hazard they're actually
    used to detect. Small enough (~a few hundred objects) that no sampling
    budget is needed — unlike Portal 01's globe, everyone is always shown."""
    cache_key = "eo_globe"
    if cache_key in _eo_globe_cache:
        return _eo_globe_cache[cache_key]

    fetched = await asyncio.gather(*(_fetch_group_tle_safe(g) for g in EO_GROUPS))
    groups_failed = [g for g, recs in zip(EO_GROUPS, fetched) if not recs]
    if len(groups_failed) == len(EO_GROUPS):
        raise HTTPException(
            status_code=502,
            detail="CelesTrak returned no Earth-observation satellite data; please retry shortly.",
        )

    tle_by_norad: dict[int, dict] = {}
    for records in fetched:
        for rec in records:
            try:
                norad_id = int(rec["line1"][2:7])
            except (ValueError, IndexError, KeyError):
                continue
            tle_by_norad[norad_id] = rec

    # Real active/inactive status, cross-referenced against SATCAT by NORAD
    # ID — optional: if SATCAT is briefly unreachable, the globe still
    # renders with positions, just without a status badge.
    status_by_norad: dict[int, str] = {}
    try:
        onorbit = await fetch_satcat_onorbit()
        for rec in onorbit:
            nid = rec.get("NORAD_CAT_ID")
            if nid in tle_by_norad:
                status_by_norad[nid] = classify_ops_status(rec.get("OPS_STATUS_CODE"))
    except Exception:
        pass

    positions = propagate_subpoints(list(tle_by_norad.values()))  # real SGP4, not estimated

    objects = []
    for norad_id, pos in positions.items():
        rec = tle_by_norad[norad_id]
        objects.append({
            "norad_id": norad_id,
            "name": rec["name"],
            "cospar_id": _cospar_id_from_tle_line1(rec["line1"]),
            "object_type": "PAYLOAD",
            "ops_status": status_by_norad.get(norad_id),
            "hazard_focus": classify_hazard_focus(rec["name"]),
            "lat": pos["lat"],
            "lon": pos["lon"],
            "alt_km": pos["alt_km"],
            "regime": classify_regime(pos.get("mean_motion")),
            "epoch": pos.get("epoch"),
            "inclination_deg": pos.get("inclination_deg"),
            "eccentricity": pos.get("eccentricity"),
            "period_min": pos.get("period_min"),
            "mean_motion_rev_day": pos.get("mean_motion_rev_day"),
            "mean_anomaly_deg": pos.get("mean_anomaly_deg"),
            "argument_of_perigee_deg": pos.get("argument_of_perigee_deg"),
            "raan_deg": pos.get("raan_deg"),
            "semi_major_axis_km": pos.get("semi_major_axis_km"),
            "perigee_alt_km": pos.get("perigee_alt_km"),
            "apogee_alt_km": pos.get("apogee_alt_km"),
        })

    result = {
        "source": EO_SOURCE,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(objects),
        "objects": objects,
        "groups_used": EO_GROUPS,
        "groups_unavailable": groups_failed,
        "note": (
            "Indicative subset from CelesTrak's own mission-category groups, not a "
            "complete Earth-observation satellite census — a full count needs a mission "
            "registry (e.g. WMO OSCAR). Hazard focus is a best-effort classification from "
            "each satellite's name against known mission patterns (e.g. TERRA/AQUA/"
            "SUOMI NPP -> Fire Detection), not an authoritative purpose field."
        ),
    }
    if objects:
        _eo_globe_cache[cache_key] = result
    return result


@router.get("/globe-objects")
async def eo_globe_objects():
    """Live 3D positions for Earth-observation satellites — same shape and
    propagation approach as Portal 01's /space-assets/globe-objects, so the
    globe component renders identically."""
    return await _eo_globe_objects()


@router.get("/types")
async def eo_types():
    """Hazard-focus breakdown: how many EO satellites are primarily used for
    fire detection, storm/weather tracking, flood/precipitation monitoring,
    vs general-purpose Earth imaging — with how many of each are active."""
    data = await _eo_globe_objects()
    counts = {label: {"total": 0, "active": 0} for label in HAZARD_FOCUS_LABELS}
    for o in data["objects"]:
        counts[o["hazard_focus"]]["total"] += 1
        if o["ops_status"] == "active":
            counts[o["hazard_focus"]]["active"] += 1
    return {
        "source": data["source"],
        "updated_at": data["updated_at"],
        "total": data["count"],
        "types": [{"label": label, **counts[label]} for label in HAZARD_FOCUS_LABELS],
        "note": data["note"],
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