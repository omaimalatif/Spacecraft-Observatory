# Portal 08 — CubeSat & Small Satellites.
# Source: CelesTrak GP catalog, GROUP=cubesat — CelesTrak's own official
# grouping of catalogued CubeSats. Unlike Portals 04/05/07, there is no
# meaningful small set of named "families" here (a cubesat catalog is
# thousands of one-off university/commercial missions with no shared naming
# convention), so rather than guessing at operator families from the name,
# the category breakdown here is computed directly from each object's own
# orbital elements — the altitude band of its orbit — which is honest,
# numeric-derived data rather than a name-pattern guess.
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

CUBESAT_GROUP = "cubesat"
CUBESAT_SOURCE = "CelesTrak GP catalog (GROUP=cubesat)"

# Altitude bands computed from each satellite's own perigee altitude — not a
# name guess. Order matters: first band whose upper bound the perigee falls
# under wins.
ALTITUDE_BANDS: list[tuple[str, float]] = [
    ("Very Low LEO (<400 km)", 400),
    ("Low LEO (400\u2013600 km)", 600),
    ("SSO Belt (600\u2013800 km)", 800),
]
HIGH_BAND = "High LEO/Other (800+ km)"
CATEGORY_ORDER = [c for c, _ in ALTITUDE_BANDS] + [HIGH_BAND]

CATEGORY_META = {
    "Very Low LEO (<400 km)": {"full_name": "Very Low LEO CubeSats", "operator": "Various — fast orbital decay (months to ~1-2 years)"},
    "Low LEO (400\u2013600 km)": {"full_name": "Low LEO CubeSats", "operator": "Various — ISS-deployment altitude band"},
    "SSO Belt (600\u2013800 km)": {"full_name": "Sun-synchronous-belt CubeSats", "operator": "Various — common Earth-imaging/remote-sensing altitude"},
    HIGH_BAND: {"full_name": "High LEO & other-orbit CubeSats", "operator": "Various — longer-lived or non-standard orbits"},
}


def classify_altitude_band(perigee_alt_km: float | None) -> str:
    if perigee_alt_km is None:
        return HIGH_BAND
    for label, upper_bound in ALTITUDE_BANDS:
        if perigee_alt_km < upper_bound:
            return label
    return HIGH_BAND


def _norad_from_tle(rec: dict) -> int | None:
    try:
        return int(rec["line1"][2:7])
    except (ValueError, IndexError, KeyError, TypeError):
        return None


async def _fetch_cubesat_json() -> list[dict]:
    try:
        return await fetch_group_json(CUBESAT_GROUP)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach CelesTrak: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


async def _fetch_cubesat_tle() -> list[dict]:
    try:
        return await fetch_group_tle(CUBESAT_GROUP)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach CelesTrak: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _orbital_elements(mean_motion, eccentricity):
    semi_major_axis_km = None
    if mean_motion:
        semi_major_axis_km = (398600.4418 / ((mean_motion * 2 * 3.141592653589793 / 86400) ** 2)) ** (1 / 3)
    perigee_alt_km = semi_major_axis_km * (1 - eccentricity) - 6378.137 if semi_major_axis_km is not None and eccentricity is not None else None
    apogee_alt_km = semi_major_axis_km * (1 + eccentricity) - 6378.137 if semi_major_axis_km is not None and eccentricity is not None else None
    return semi_major_axis_km, perigee_alt_km, apogee_alt_km


def _shape_satellite(item: dict) -> dict:
    name = item.get("OBJECT_NAME")
    mean_motion = item.get("MEAN_MOTION")
    inclination = item.get("INCLINATION")
    eccentricity = item.get("ECCENTRICITY")
    semi_major_axis_km, perigee_alt_km, apogee_alt_km = _orbital_elements(mean_motion, eccentricity)
    return {
        "name": name,
        "norad_id": item.get("NORAD_CAT_ID"),
        "cospar_id": item.get("OBJECT_ID"),
        "category": classify_altitude_band(perigee_alt_km),
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
    items = await _fetch_cubesat_json()
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
        "source": CUBESAT_SOURCE,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "notes": {
            "categories": "Group membership (cubesat) is CelesTrak's own official grouping. Category bands are each satellite's own computed perigee altitude, not a name guess — CubeSat missions have no shared naming convention to classify by.",
        },
    }


@router.get("/categories")
async def categories():
    items = await _fetch_cubesat_json()
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
        "source": CUBESAT_SOURCE,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/satellites")
async def satellites(
    category: str | None = Query(None, description="Filter by altitude-band category"),
    q: str | None = Query(None, min_length=1, max_length=80, description="Free-text search over satellite name"),
    limit: int = Query(500, le=2000),
):
    items = await _fetch_cubesat_json()
    shaped = [_shape_satellite(item) for item in items]

    if category:
        shaped = [s for s in shaped if s["category"].lower() == category.lower()]
    if q:
        needle = q.strip().lower()
        shaped = [s for s in shaped if needle in str(s["name"] or "").lower() or needle in str(s["norad_id"] or "")]

    return {
        "count": len(shaped),
        "satellites": shaped[:limit],
        "source": CUBESAT_SOURCE,
    }


_globe_cache = TTLCache(maxsize=2, ttl=300)


async def _propagated_cubesat_objects() -> dict:
    cache_key = "cubesat_globe"
    if cache_key in _globe_cache:
        return _globe_cache[cache_key]

    tle_records = await _fetch_cubesat_tle()
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
            "category": classify_altitude_band(pos.get("perigee_alt_km")),
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
        "source": CUBESAT_SOURCE + ", SGP4-propagated (Skyfield) at request time",
        "count": len(objects),
        "objects": objects,
    }
    _globe_cache[cache_key] = result
    return result


@router.get("/globe-objects")
async def globe_objects():
    try:
        return await _propagated_cubesat_objects()
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
    cache_key = "cubesat_orbit_paths"
    if cache_key in _orbit_paths_cache:
        return _orbit_paths_cache[cache_key]

    tle_records = await _fetch_cubesat_tle()

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
            "period_min": entry["period_min"],
            "path": entry["path"],
        })

    result = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "source": CUBESAT_SOURCE + ", SGP4-propagated (Skyfield) — one full orbital period per satellite",
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
    tle_records = await _fetch_cubesat_tle()

    visible = compute_visible(tle_records, lat, lon, min_elevation_deg=min_elevation_deg, limit=500)

    by_category: dict[str, int] = {}
    for sat in visible:
        # compute_visible() doesn't return an instantaneous altitude, only
        # the orbit's mean perigee — same figure /overview and /satellites
        # use, so the band is consistent across every endpoint.
        category = classify_altitude_band(sat.get("perigee_alt_km"))
        sat["category"] = category
        by_category[category] = by_category.get(category, 0) + 1

    return {
        "location": {"lat": lat, "lon": lon},
        "min_elevation_deg": min_elevation_deg,
        "visible_count": len(visible),
        "catalog_size": len(tle_records),
        "by_category": by_category,
        "satellites": visible,
        "source": CUBESAT_SOURCE + " + Skyfield SGP4, computed at request time",
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
    tle_records = await _fetch_cubesat_tle()

    visible = compute_visible(tle_records, lat, lon, min_elevation_deg=min_elevation_deg, limit=500)
    visible_norad_ids = {sat["norad_id"] for sat in visible}
    category_by_norad = {sat["norad_id"]: classify_altitude_band(sat.get("perigee_alt_km")) for sat in visible}

    visible_tle_records = [rec for rec in tle_records if _norad_from_tle(rec) in visible_norad_ids]

    tracks = compute_sky_tracks_batch(visible_tle_records, lat, lon, elevation_m, window_min=window_min)
    return {
        "location": {"lat": lat, "lon": lon},
        "window_min": window_min,
        "tracks": {
            str(norad_id): {"category": category_by_norad.get(norad_id, HIGH_BAND), "points": points}
            for norad_id, points in tracks.items()
        },
        "source": CUBESAT_SOURCE + " + Skyfield SGP4, computed at request time",
    }


SERVICE_INFO = [
    {
        "category": "Very Low LEO (<400 km)", "full_name": "Very Low LEO CubeSats",
        "operator": "Various universities, agencies and commercial operators", "status": "Fastest orbital decay band",
        "orbital_regime": "LEO", "altitude_km": 350, "fleet_size_note": "Typically ISS-deployed or newly launched missions still descending",
        "services": ["Technology demonstration", "Short-duration student/educational missions"],
        "source": "CelesTrak", "source_url": "https://celestrak.org/",
    },
    {
        "category": "Low LEO (400\u2013600 km)", "full_name": "Low LEO CubeSats",
        "operator": "Various", "status": "Common ISS-deployment altitude band",
        "orbital_regime": "LEO", "altitude_km": 500, "fleet_size_note": "Many ISS-deployed CubeSats settle in this band after release",
        "services": ["Technology demonstration", "Amateur radio", "Educational payloads"],
        "source": "CelesTrak", "source_url": "https://celestrak.org/",
    },
    {
        "category": "SSO Belt (600\u2013800 km)", "full_name": "Sun-synchronous-belt CubeSats",
        "operator": "Various commercial & agency operators", "status": "Popular altitude for imaging/remote-sensing constellations",
        "orbital_regime": "LEO", "altitude_km": 700, "fleet_size_note": "Includes many commercial Earth-imaging CubeSat constellations",
        "services": ["Earth imaging / remote sensing", "IoT data relay", "Space weather / science instruments"],
        "source": "CelesTrak", "source_url": "https://celestrak.org/",
    },
    {
        "category": HIGH_BAND, "full_name": "High LEO & other-orbit CubeSats",
        "operator": "Various", "status": "Longer-lived orbits or non-standard orbital regimes",
        "orbital_regime": "LEO (high) / other", "altitude_km": 900, "fleet_size_note": "A smaller share of the catalog — includes longer-duration missions",
        "services": ["Extended technology demonstration", "Science instruments requiring longer mission life"],
        "source": "CelesTrak", "source_url": "https://celestrak.org/",
    },
]


@router.get("/service-info")
def service_info():
    return {
        "categories": SERVICE_INFO,
        "is_static_reference_data": True,
        "excluded_note": "Altitude bands are computed from each satellite's own orbital elements at request time, not a fixed roster — a satellite's band can shift over its mission as its orbit decays.",
        "note": "Reference notes about each altitude band — not live telemetry. Live satellite counts and positions come from /overview, /categories and /globe-objects instead.",
    }
