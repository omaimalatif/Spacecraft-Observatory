# Portal 07 add-on — Human Spaceflight satellite tracking.
# Source: CelesTrak GP catalog, GROUP=stations — CelesTrak's own official
# grouping of crewed space stations, their docked/berthed modules, and the
# crew/cargo vehicles currently attached to or en route to them (plus a
# handful of small satellites deployed from the ISS and associated debris
# that CelesTrak also files under this group). Group membership is
# authoritative; the family labels below (ISS Segment, Tiangong Segment,
# Crew & Cargo Vehicles) are derived by matching each object's name against
# well-known module/vehicle name patterns within that single group — same
# honest pattern as Portal 05's weather-group family classification.
# The plain human-readable ISS position / crew roster (Open Notify) lives in
# the sibling human_spaceflight.py router — this file is purely the live
# orbital-tracking layer (globe, sky plot, search) for the same portal.
from __future__ import annotations

from datetime import datetime, timezone

import httpx
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException, Query

from app.services.celestrak import fetch_group_json, fetch_group_tle, fetch_object_tle
from app.services.orbital import (
    classify_regime,
    compute_orbit_path,
    compute_orbit_paths_batch,
    compute_sky_track,
    compute_sky_tracks_batch,
    compute_visible,
    propagate_subpoints,
)

router = APIRouter()

STATIONS_GROUP = "stations"
HSF_SOURCE = "CelesTrak GP catalog (GROUP=stations)"

FAMILY_PATTERNS: list[tuple[str, list[str]]] = [
    ("ISS Segment", ["ISS ", "ISS(", "ZARYA", "POISK", "NAUKA", "ZVEZDA", "UNITY", "DESTINY", "COLUMBUS", "KIBO", "TRANQUILITY", "HARMONY", "CUPOLA"]),
    ("Tiangong (CSS) Segment", ["CSS ", "CSS(", "TIANHE", "WENTIAN", "MENGTIAN"]),
    ("Crew & Cargo Vehicles", ["DRAGON", "PROGRESS", "CYGNUS", "TIANZHOU", "SHENZHOU", "SOYUZ", "STARLINER"]),
]
CATEGORY_ORDER = [c for c, _ in FAMILY_PATTERNS] + ["Other"]

CATEGORY_META = {
    "ISS Segment": {"full_name": "International Space Station", "operator": "NASA / Roscosmos / ESA / JAXA / CSA"},
    "Tiangong (CSS) Segment": {"full_name": "Tiangong Space Station (CSS)", "operator": "China Manned Space Agency (CMSA)"},
    "Crew & Cargo Vehicles": {"full_name": "Crew & cargo resupply spacecraft", "operator": "SpaceX / Roscosmos / Northrop Grumman / CMSA"},
    "Other": {"full_name": "Deployed small satellites & associated debris", "operator": "Various (university/agency payloads deployed from ISS)"},
}


def classify_family(name: str | None) -> str:
    upper = (name or "").upper()
    for category, patterns in FAMILY_PATTERNS:
        if any(p in upper for p in patterns):
            return category
    return "Other"


def _norad_from_tle(rec: dict) -> int | None:
    try:
        return int(rec["line1"][2:7])
    except (ValueError, IndexError, KeyError, TypeError):
        return None


async def _fetch_stations_json() -> list[dict]:
    try:
        return await fetch_group_json(STATIONS_GROUP)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach CelesTrak: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


async def _fetch_stations_tle() -> list[dict]:
    try:
        return await fetch_group_tle(STATIONS_GROUP)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach CelesTrak: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _shape_satellite(item: dict) -> dict:
    name = item.get("OBJECT_NAME")
    mean_motion = item.get("MEAN_MOTION")
    inclination = item.get("INCLINATION")
    eccentricity = item.get("ECCENTRICITY")
    semi_major_axis_km = None
    if mean_motion:
        semi_major_axis_km = (398600.4418 / ((mean_motion * 2 * 3.141592653589793 / 86400) ** 2)) ** (1 / 3)
    perigee_alt_km = semi_major_axis_km * (1 - eccentricity) - 6378.137 if semi_major_axis_km is not None and eccentricity is not None else None
    apogee_alt_km = semi_major_axis_km * (1 + eccentricity) - 6378.137 if semi_major_axis_km is not None and eccentricity is not None else None
    return {
        "name": name,
        "norad_id": item.get("NORAD_CAT_ID"),
        "cospar_id": item.get("OBJECT_ID"),
        "category": classify_family(name),
        "regime": classify_regime(mean_motion),
        "inclination_deg": inclination,
        "period_min": round(1440 / mean_motion, 1) if mean_motion else None,
        "mean_motion_rev_day": mean_motion,
        "eccentricity": eccentricity,
        "mean_anomaly_deg": item.get("MEAN_ANOMALY"),
        "argument_of_perigee_deg": item.get("ARG_OF_PERICENTER"),
        "raan_deg": item.get("RA_OF_ASC_NODE"),
        "semi_major_axis_km": round(semi_major_axis_km, 1) if semi_major_axis_km is not None else None,
        "perigee_alt_km": round(perigee_alt_km, 1) if perigee_alt_km is not None else None,
        "apogee_alt_km": round(apogee_alt_km, 1) if apogee_alt_km is not None else None,
        "epoch": item.get("EPOCH"),
    }


@router.get("/overview")
async def overview():
    items = await _fetch_stations_json()
    shaped = [_shape_satellite(item) for item in items]

    by_category: dict[str, int] = {}
    by_regime: dict[str, int] = {}
    for sat in shaped:
        by_category[sat["category"]] = by_category.get(sat["category"], 0) + 1
        by_regime[sat["regime"]] = by_regime.get(sat["regime"], 0) + 1

    active_categories = [c for c in CATEGORY_ORDER if by_category.get(c, 0) > 0]

    return {
        "total_satellites": len(shaped),
        "category_count": len(active_categories),
        "categories": active_categories,
        "by_category": by_category,
        "by_regime": by_regime,
        "source": HSF_SOURCE,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "notes": {
            "categories": "Group membership (stations) is CelesTrak's own official grouping. Family labels (ISS Segment, Tiangong Segment, Crew & Cargo Vehicles) within that group are derived from name-pattern matching, not upstream metadata.",
        },
    }


@router.get("/categories")
async def categories():
    items = await _fetch_stations_json()
    shaped = [_shape_satellite(item) for item in items]

    groups: dict[str, dict] = {}
    for sat in shaped:
        key = sat["category"]
        entry = groups.setdefault(key, {
            "category": key,
            **CATEGORY_META.get(key, {"full_name": key, "operator": "Unknown"}),
            "satellite_count": 0,
            "by_regime": {},
        })
        entry["satellite_count"] += 1
        entry["by_regime"][sat["regime"]] = entry["by_regime"].get(sat["regime"], 0) + 1

    ordered = [groups[c] for c in CATEGORY_ORDER if c in groups]

    return {
        "total": len(shaped),
        "categories": ordered,
        "source": HSF_SOURCE,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/satellites")
async def satellites(
    category: str | None = Query(None, description="Filter by category, e.g. ISS Segment, Tiangong (CSS) Segment"),
    q: str | None = Query(None, min_length=1, max_length=80, description="Free-text search over satellite name"),
    limit: int = Query(500, le=2000),
):
    items = await _fetch_stations_json()
    shaped = [_shape_satellite(item) for item in items]

    if category:
        shaped = [s for s in shaped if s["category"].lower() == category.lower()]
    if q:
        needle = q.strip().lower()
        shaped = [s for s in shaped if needle in str(s["name"] or "").lower() or needle in str(s["norad_id"] or "")]

    return {
        "count": len(shaped),
        "satellites": shaped[:limit],
        "source": HSF_SOURCE,
    }


_globe_cache = TTLCache(maxsize=2, ttl=300)


async def _propagated_hsf_objects() -> dict:
    cache_key = "hsf_globe"
    if cache_key in _globe_cache:
        return _globe_cache[cache_key]

    tle_records = await _fetch_stations_tle()
    category_by_norad = {n: classify_family(rec["name"]) for rec in tle_records if (n := _norad_from_tle(rec)) is not None}

    positions = propagate_subpoints(tle_records)

    by_norad_tle = {}
    for rec in tle_records:
        norad_id = _norad_from_tle(rec)
        if norad_id is not None:
            by_norad_tle[norad_id] = rec

    objects = []
    for norad_id, pos in positions.items():
        rec = by_norad_tle.get(norad_id)
        if not rec:
            continue
        objects.append({
            "norad_id": norad_id,
            "name": rec["name"],
            "category": category_by_norad.get(norad_id, "Other"),
            "regime": classify_regime(pos.get("mean_motion")),
            "lat": pos["lat"],
            "lon": pos["lon"],
            "alt_km": pos["alt_km"],
            "inclination_deg": pos.get("inclination_deg"),
            "period_min": pos.get("period_min"),
            "epoch": pos.get("epoch"),
            "mean_motion_rev_day": pos.get("mean_motion_rev_day"),
            "eccentricity": pos.get("eccentricity"),
            "mean_anomaly_deg": pos.get("mean_anomaly_deg"),
            "argument_of_perigee_deg": pos.get("argument_of_perigee_deg"),
            "raan_deg": pos.get("raan_deg"),
            "semi_major_axis_km": pos.get("semi_major_axis_km"),
            "perigee_alt_km": pos.get("perigee_alt_km"),
            "apogee_alt_km": pos.get("apogee_alt_km"),
        })

    result = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "source": HSF_SOURCE + ", SGP4-propagated (Skyfield) at request time",
        "count": len(objects),
        "objects": objects,
    }
    _globe_cache[cache_key] = result
    return result


@router.get("/globe-objects")
async def globe_objects():
    try:
        return await _propagated_hsf_objects()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach CelesTrak: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/orbit-path/{norad_id}")
async def orbit_path(norad_id: int):
    try:
        tle = await fetch_object_tle(norad_id)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach CelesTrak: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if tle is None:
        raise HTTPException(status_code=404, detail="No propagatable elements for this object (decayed, or not in CelesTrak's free GP feed).")

    path = compute_orbit_path(tle["line1"], tle["line2"], tle["name"])
    if not path:
        raise HTTPException(status_code=422, detail="Could not compute an orbit path from this object's elements.")

    return {
        "norad_id": norad_id,
        "name": tle["name"],
        "source": "CelesTrak, SGP4-propagated",
        "path": path,
    }


_orbit_paths_cache = TTLCache(maxsize=2, ttl=300)


@router.get("/orbit-paths")
async def orbit_paths():
    cache_key = "hsf_orbit_paths"
    if cache_key in _orbit_paths_cache:
        return _orbit_paths_cache[cache_key]

    tle_records = await _fetch_stations_tle()
    category_by_norad = {n: classify_family(rec["name"]) for rec in tle_records if (n := _norad_from_tle(rec)) is not None}

    by_norad_tle = {}
    for rec in tle_records:
        norad_id = _norad_from_tle(rec)
        if norad_id is not None:
            by_norad_tle[norad_id] = rec

    paths = compute_orbit_paths_batch(tle_records)
    objects = []
    for norad_id, entry in paths.items():
        rec = by_norad_tle.get(norad_id)
        if not rec:
            continue
        objects.append({
            "norad_id": norad_id,
            "name": rec["name"],
            "category": category_by_norad.get(norad_id, "Other"),
            "period_min": entry["period_min"],
            "path": entry["path"],
        })

    result = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "source": HSF_SOURCE + ", SGP4-propagated (Skyfield) — one full orbital period per satellite",
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
    tle_records = await _fetch_stations_tle()
    category_by_norad = {n: classify_family(rec["name"]) for rec in tle_records if (n := _norad_from_tle(rec)) is not None}

    visible = compute_visible(tle_records, lat, lon, min_elevation_deg=min_elevation_deg, limit=500)
    by_category: dict[str, int] = {}
    for sat in visible:
        sat["category"] = category_by_norad.get(sat["norad_id"], "Other")
        by_category[sat["category"]] = by_category.get(sat["category"], 0) + 1

    return {
        "location": {"lat": lat, "lon": lon},
        "min_elevation_deg": min_elevation_deg,
        "visible_count": len(visible),
        "catalog_size": len(tle_records),
        "by_category": by_category,
        "satellites": visible,
        "source": HSF_SOURCE + " + Skyfield SGP4, computed at request time",
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
        "window_min": window_min,
        "track": track,
        "source": "CelesTrak + Skyfield SGP4, computed at request time",
    }


@router.get("/sky-tracks")
async def sky_tracks(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    min_elevation_deg: float = Query(10, ge=0, le=90),
    elevation_m: float = Query(0),
    window_min: int = Query(25, ge=5, le=90),
):
    tle_records = await _fetch_stations_tle()
    category_by_norad = {n: classify_family(rec["name"]) for rec in tle_records if (n := _norad_from_tle(rec)) is not None}

    visible = compute_visible(tle_records, lat, lon, min_elevation_deg=min_elevation_deg, limit=500)
    visible_norad_ids = {sat["norad_id"] for sat in visible}

    visible_tle_records = [rec for rec in tle_records if _norad_from_tle(rec) in visible_norad_ids]

    tracks = compute_sky_tracks_batch(visible_tle_records, lat, lon, elevation_m, window_min=window_min)
    return {
        "location": {"lat": lat, "lon": lon},
        "window_min": window_min,
        "tracks": {
            str(norad_id): {"category": category_by_norad.get(norad_id, "Other"), "points": points}
            for norad_id, points in tracks.items()
        },
        "source": HSF_SOURCE + " + Skyfield SGP4, computed at request time",
    }


SERVICE_INFO = [
    {
        "category": "ISS Segment", "full_name": "International Space Station",
        "operator": "NASA / Roscosmos / ESA / JAXA / CSA", "status": "Continuously crewed since November 2000",
        "orbital_regime": "LEO", "altitude_km": 420, "fleet_size_note": "One station; core modules plus Progress/Soyuz/Dragon/Cygnus visiting vehicles counted separately",
        "services": ["Microgravity research", "Long-duration human spaceflight operations", "Technology demonstration"],
        "source": "NASA", "source_url": "https://www.nasa.gov/international-space-station/",
    },
    {
        "category": "Tiangong (CSS) Segment", "full_name": "Tiangong Space Station",
        "operator": "China Manned Space Agency (CMSA)", "status": "Continuously crewed since 2022 (T-shaped 3-module configuration)",
        "orbital_regime": "LEO", "altitude_km": 390, "fleet_size_note": "Core module (Tianhe) plus two lab modules (Wentian, Mengtian)",
        "services": ["Microgravity & life-science research", "Crewed operations", "International payload hosting"],
        "source": "China Manned Space Agency", "source_url": "http://en.cmse.gov.cn/",
    },
    {
        "category": "Crew & Cargo Vehicles", "full_name": "Crew & cargo resupply spacecraft",
        "operator": "SpaceX / Roscosmos / Northrop Grumman / CMSA", "status": "Operational — vehicles rotate as missions launch/return",
        "orbital_regime": "LEO", "altitude_km": 420, "fleet_size_note": "Number in-orbit varies with the current launch/docking schedule",
        "services": ["Crew rotation (Crew Dragon, Soyuz, Shenzhou)", "Pressurized/unpressurized cargo resupply (Progress, Cygnus, Tianzhou)", "Station reboost & waste disposal"],
        "source": "NASA / Roscosmos / Northrop Grumman", "source_url": "https://www.nasa.gov/humans-in-space/",
    },
]

OTHER_NOTE = (
    "The 'Other' category groups additional objects CelesTrak also files under the stations group: "
    "small satellites deployed by astronauts from the ISS (e.g. university CubeSats) and tracked "
    "debris/hardware associated with station or crew-vehicle operations."
)


@router.get("/service-info")
def service_info():
    return {
        "categories": SERVICE_INFO,
        "is_static_reference_data": True,
        "excluded_note": OTHER_NOTE,
        "note": "Published mission facts from each agency's own site — not live telemetry. Live satellite counts and positions come from /overview, /categories and /globe-objects instead.",
    }
