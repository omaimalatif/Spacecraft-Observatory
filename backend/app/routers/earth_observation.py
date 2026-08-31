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
from app.services.celestrak import fetch_group_json, fetch_group_tle, fetch_object_tle
from app.services.eo_taxonomy import HAZARD_FOCUS_LABELS, classify_hazard_focus
from app.services.firms import FirmsNotConfigured, fetch_fires, is_configured
from app.services.orbital import (
    classify_regime,
    compute_orbit_path,
    compute_orbit_paths_batch,
    compute_sky_track,
    compute_sky_tracks_batch,
    compute_visible,
    propagate_subpoints,
)
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


# --- Sky plotting / map-click availability (same pattern as Portals 03-08) --
def _norad_from_tle(rec: dict) -> int | None:
    try:
        return int(rec["line1"][2:7])
    except (ValueError, IndexError, KeyError, TypeError):
        return None


async def _fetch_all_eo_tle() -> list[dict]:
    """TLE records across both EO groups (resource + weather), deduplicated
    by NORAD ID. Only two groups, so — like the existing globe-objects
    fetch above — these are fetched concurrently rather than paced
    sequentially (the sequential/paced approach elsewhere in this app is for
    portals fetching many more groups at once, e.g. Communication's eight)."""
    fetched = await asyncio.gather(*(_fetch_group_tle_safe(g) for g in EO_GROUPS))
    seen: set[int] = set()
    records: list[dict] = []
    for group_records in fetched:
        for rec in group_records:
            norad_id = _norad_from_tle(rec)
            if norad_id is None or norad_id in seen:
                continue
            seen.add(norad_id)
            records.append(rec)
    return records


_orbit_paths_cache = TTLCache(maxsize=2, ttl=300)


@router.get("/orbit-paths")
async def orbit_paths():
    cache_key = "eo_orbit_paths"
    if cache_key in _orbit_paths_cache:
        return _orbit_paths_cache[cache_key]

    tle_records = await _fetch_all_eo_tle()
    hazard_by_norad = {n: classify_hazard_focus(rec["name"]) for rec in tle_records if (n := _norad_from_tle(rec)) is not None}
    by_norad_tle = {n: rec for rec in tle_records if (n := _norad_from_tle(rec)) is not None}

    paths = compute_orbit_paths_batch(tle_records)
    objects = []
    for norad_id, entry in paths.items():
        rec = by_norad_tle.get(norad_id)
        if not rec:
            continue
        objects.append({
            "norad_id": norad_id,
            "name": rec["name"],
            "hazard_focus": hazard_by_norad.get(norad_id, "General Earth Observation"),
            "period_min": entry["period_min"],
            "path": entry["path"],
        })

    result = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "source": EO_SOURCE + " — one full orbital period per satellite",
        "count": len(objects),
        "objects": objects,
    }
    _orbit_paths_cache[cache_key] = result
    return result


@router.get("/availability")
async def availability(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    min_elevation_deg: float = Query(10, ge=0, le=90),
):
    tle_records = await _fetch_all_eo_tle()
    hazard_by_norad = {n: classify_hazard_focus(rec["name"]) for rec in tle_records if (n := _norad_from_tle(rec)) is not None}

    visible = compute_visible(tle_records, lat, lon, min_elevation_deg=min_elevation_deg, limit=500)
    by_category: dict[str, int] = {}
    for sat in visible:
        sat["category"] = hazard_by_norad.get(sat["norad_id"], "General Earth Observation")
        by_category[sat["category"]] = by_category.get(sat["category"], 0) + 1

    return {
        "location": {"lat": lat, "lon": lon},
        "min_elevation_deg": min_elevation_deg,
        "visible_count": len(visible),
        "catalog_size": len(tle_records),
        "by_category": by_category,
        "satellites": visible,
        "source": EO_SOURCE + ", computed at request time",
    }


@router.get("/sky-track/{norad_id}")
async def sky_track(
    norad_id: int,
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    elevation_m: float = Query(0),
    window_min: int = Query(60, ge=5, le=180),
):
    try:
        tle = await fetch_object_tle(norad_id)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach CelesTrak: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if tle is None:
        raise HTTPException(status_code=404, detail="No propagatable elements for this object (decayed, or not in CelesTrak's free GP feed).")

    track = compute_sky_track(tle["line1"], tle["line2"], tle["name"], lat, lon, elevation_m, window_min=window_min)
    return {
        "norad_id": norad_id,
        "name": tle["name"],
        "category": classify_hazard_focus(tle["name"]),
        "window_min": window_min,
        "track": track,
        "source": "CelesTrak resource/weather groups + Skyfield SGP4, computed at request time",
    }


@router.get("/sky-tracks")
async def sky_tracks(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    min_elevation_deg: float = Query(10, ge=0, le=90),
    elevation_m: float = Query(0),
    window_min: int = Query(25, ge=5, le=90),
):
    tle_records = await _fetch_all_eo_tle()
    hazard_by_norad = {n: classify_hazard_focus(rec["name"]) for rec in tle_records if (n := _norad_from_tle(rec)) is not None}

    visible = compute_visible(tle_records, lat, lon, min_elevation_deg=min_elevation_deg, limit=500)
    visible_norad_ids = {sat["norad_id"] for sat in visible}
    visible_tle_records = [rec for rec in tle_records if _norad_from_tle(rec) in visible_norad_ids]

    tracks = compute_sky_tracks_batch(visible_tle_records, lat, lon, elevation_m, window_min=window_min)
    return {
        "location": {"lat": lat, "lon": lon},
        "window_min": window_min,
        "tracks": {
            str(norad_id): {"category": hazard_by_norad.get(norad_id, "General Earth Observation"), "points": points}
            for norad_id, points in tracks.items()
        },
        "source": EO_SOURCE + ", computed at request time",
    }


# --- Static reference data: published context, NOT live telemetry ----------
SERVICE_INFO = [
    {
        "category": "Fire Detection", "full_name": "Fire Detection",
        "description": "Satellites carrying the MODIS and VIIRS instruments that NASA FIRMS itself draws active-fire and thermal-anomaly detections from.",
        "example_missions": ["Terra", "Aqua", "Suomi NPP", "NOAA-20", "NOAA-21"],
        "source": "NASA FIRMS", "source_url": "https://firms.modaps.eosdis.nasa.gov/",
    },
    {
        "category": "Storm & Weather Tracking", "full_name": "Storm & Weather Tracking",
        "description": "Geostationary and polar-orbiting weather satellites used for storm tracking, cloud imagery and numerical weather prediction.",
        "example_missions": ["GOES", "Meteosat / MTG", "Himawari", "Fengyun", "Metop"],
        "source": "NOAA / EUMETSAT", "source_url": "https://www.nesdis.noaa.gov/",
    },
    {
        "category": "Flood & Precipitation Monitoring", "full_name": "Flood & Precipitation Monitoring",
        "description": "Radar and microwave satellites used for precipitation measurement, soil moisture and flood-extent mapping.",
        "example_missions": ["GPM", "Sentinel-1", "SMAP", "SWOT", "ICEYE"],
        "source": "NASA / ESA Copernicus", "source_url": "https://gpm.nasa.gov/",
    },
    {
        "category": "General Earth Observation", "full_name": "General Earth Observation",
        "description": "Catalogued by CelesTrak under its resource or weather groups but not confidently matched to a specific hazard-focus mission pattern above.",
        "example_missions": [],
        "source": "CelesTrak", "source_url": "https://celestrak.org/",
    },
]


@router.get("/service-info")
def service_info():
    return {
        "categories": SERVICE_INFO,
        "is_static_reference_data": True,
        "note": "General mission-family context from public agency pages — not live telemetry. Live satellite counts and positions come from /types, /satellites and /globe-objects instead.",
    }


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
async def satellites(
    category: str | None = Query(None, description="Filter by hazard focus, e.g. 'Fire Detection'"),
    q: str | None = Query(None, min_length=1, max_length=80, description="Free-text search over satellite name"),
    limit: int = Query(500, le=2000),
):
    """
    Earth-observation satellite count from CelesTrak's public GP groups that
    map to EO missions (resource + weather). This is an indicative subset of
    CelesTrak's own categorization, not a complete or authoritative EO census
    — a full count would need a mission-registry source (e.g. WMO OSCAR).

    Also supports searching/filtering the live catalog (q / category / limit)
    for the portal's satellite-search box, same as the other satellite-
    tracking portals.
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

    data = await _eo_globe_objects()
    shaped = [{**o, "category": o["hazard_focus"]} for o in data["objects"]]
    if category:
        shaped = [s for s in shaped if s["category"].lower() == category.lower()]
    if q:
        needle = q.strip().lower()
        shaped = [s for s in shaped if needle in str(s["name"] or "").lower() or needle in str(s["norad_id"] or "")]

    return {
        "earth_resources_satellites": len(resource),
        "weather_satellites": len(weather),
        "total": len(resource) + len(weather),
        "count": len(shaped),
        "satellites": shaped[:limit],
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