# Portal 06 add-on — Space Science satellite tracking.
# Source: CelesTrak GP catalog, GROUP=science ("Space & Earth Science") — the
# same live-data + SGP4-propagation pattern as Portal 03 (Navigation). This
# sits alongside the existing /api/space-science/* (JPL Horizons deep-space
# ephemerides) endpoints in space_science.py without touching them; this
# router only covers Earth-orbiting science satellites that CelesTrak
# actually tracks with TLEs, which deep-space probes are not.
#
# CelesTrak's science group is a flat list with no official sub-categories,
# so satellites are grouped into broad, disclosed-as-best-effort mission
# families from their public names (a well-known technique for a handful of
# flagship missions; everything else falls into "Other / Unclassified"
# rather than being force-fit into a family it may not belong to).
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

SCI_GROUP = "science"
SCI_SOURCE = "CelesTrak GP catalog (GROUP=science)"

CATEGORY_ORDER = [
    "Astrophysics & Astronomy",
    "Heliophysics & Space Weather",
    "Earth & Climate Science",
    "Technology Demonstration",
    "Other / Unclassified",
]

CATEGORY_META = {
    "Astrophysics & Astronomy": {"full_name": "Astrophysics & Astronomy", "focus": "Telescopes and observatories studying stars, galaxies, and the wider universe."},
    "Heliophysics & Space Weather": {"full_name": "Heliophysics & Space Weather", "focus": "Missions studying the Sun, the solar wind, and near-Earth space weather."},
    "Earth & Climate Science": {"full_name": "Earth & Climate Science", "focus": "Missions studying Earth's ice, oceans, atmosphere and climate from orbit."},
    "Technology Demonstration": {"full_name": "Technology Demonstration", "focus": "Small satellites and CubeSats testing new science instruments or spacecraft technology."},
    "Other / Unclassified": {"full_name": "Other / Unclassified", "focus": "Catalogued in CelesTrak's science group but not confidently matched to a family above from its name alone."},
}

# Best-effort name-substring matches for well-known, publicly documented
# missions. Anything not matched here is left as "Other / Unclassified"
# rather than guessed.
_ASTRO_TOKENS = ("HST", "HUBBLE", "IBEX", "GALEX", "SWIFT", "NUSTAR", "TESS", "IXPE", "SPEKTR")
_HELIO_TOKENS = ("SOHO", "ACE", "WIND", "TIMED", "SORCE", "AIM", "RHESSI", "TRACE", "DSCOVR", "PROBA-2", "GOES")
_EARTH_TOKENS = ("ICESAT", "CALIPSO", "CLOUDSAT", "GRACE", "JASON", "SWOT", "CYGNSS", "QUIKSCAT", "SMAP", "AURA", "TERRA", "AQUA", "SENTINEL")
_TECH_TOKENS = ("CUTE", "AAUSAT", "CUBESAT", "CUBE", "SMALLSAT", "DEMO", "TECHNOSAT", "PROBA")


def classify_science_category(name: str) -> str:
    n = (name or "").upper()
    if any(tok in n for tok in _ASTRO_TOKENS):
        return "Astrophysics & Astronomy"
    if any(tok in n for tok in _HELIO_TOKENS):
        return "Heliophysics & Space Weather"
    if any(tok in n for tok in _EARTH_TOKENS):
        return "Earth & Climate Science"
    if any(tok in n for tok in _TECH_TOKENS):
        return "Technology Demonstration"
    return "Other / Unclassified"


def _norad_from_tle(rec: dict) -> int | None:
    try:
        return int(rec["line1"][2:7])
    except (ValueError, IndexError, KeyError, TypeError):
        return None


async def _safe_fetch_group_json() -> list[dict]:
    try:
        return await fetch_group_json(SCI_GROUP)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach CelesTrak (GROUP={SCI_GROUP}): {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


async def _safe_fetch_group_tle() -> list[dict]:
    try:
        return await fetch_group_tle(SCI_GROUP)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach CelesTrak (GROUP={SCI_GROUP}): {exc}") from exc
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
        "category": classify_science_category(name),
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
    data = await _safe_fetch_group_json()
    shaped = [_shape_satellite(item) for item in data]

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
        "source": SCI_SOURCE,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "notes": {
            "categories": "Best-effort mission-family grouping from public satellite names; CelesTrak's science group has no official sub-categories of its own.",
        },
    }


@router.get("/categories")
async def categories():
    data = await _safe_fetch_group_json()
    shaped = [_shape_satellite(item) for item in data]

    groups: dict[str, dict] = {}
    for sat in shaped:
        key = sat["category"]
        entry = groups.setdefault(key, {
            "category": key,
            **CATEGORY_META.get(key, {"full_name": key, "focus": ""}),
            "satellite_count": 0,
            "by_regime": {},
        })
        entry["satellite_count"] += 1
        entry["by_regime"][sat["regime"]] = entry["by_regime"].get(sat["regime"], 0) + 1

    ordered = [groups[c] for c in CATEGORY_ORDER if c in groups]

    return {
        "total": len(shaped),
        "categories": ordered,
        "source": SCI_SOURCE,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/satellites")
async def satellites(
    category: str | None = Query(None, description="Filter by category, e.g. 'Earth & Climate Science'"),
    q: str | None = Query(None, min_length=1, max_length=80, description="Free-text search over satellite name"),
    limit: int = Query(500, le=2000),
):
    data = await _safe_fetch_group_json()
    shaped = [_shape_satellite(item) for item in data]

    if category:
        shaped = [s for s in shaped if s["category"].lower() == category.lower()]
    if q:
        needle = q.strip().lower()
        shaped = [s for s in shaped if needle in str(s["name"] or "").lower() or needle in str(s["norad_id"] or "")]

    return {
        "count": len(shaped),
        "satellites": shaped[:limit],
        "source": SCI_SOURCE,
    }


_globe_cache = TTLCache(maxsize=2, ttl=300)


async def _propagated_sci_objects() -> dict:
    cache_key = "sci_globe"
    if cache_key in _globe_cache:
        return _globe_cache[cache_key]

    tle_records = await _safe_fetch_group_tle()
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
            "category": classify_science_category(rec["name"]),
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
        "source": SCI_SOURCE + ", SGP4-propagated (Skyfield) at request time",
        "count": len(objects),
        "objects": objects,
    }
    _globe_cache[cache_key] = result
    return result


@router.get("/globe-objects")
async def globe_objects():
    try:
        return await _propagated_sci_objects()
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
        "category": classify_science_category(tle["name"]),
        "source": "CelesTrak science group, SGP4-propagated",
        "path": path,
    }


_orbit_paths_cache = TTLCache(maxsize=2, ttl=300)


@router.get("/orbit-paths")
async def orbit_paths():
    cache_key = "sci_orbit_paths"
    if cache_key in _orbit_paths_cache:
        return _orbit_paths_cache[cache_key]

    tle_records = await _safe_fetch_group_tle()
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
            "category": classify_science_category(rec["name"]),
            "period_min": entry["period_min"],
            "path": entry["path"],
        })

    result = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "source": SCI_SOURCE + ", SGP4-propagated (Skyfield) — one full orbital period per satellite",
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
    tle_records = await _safe_fetch_group_tle()

    visible = compute_visible(tle_records, lat, lon, min_elevation_deg=min_elevation_deg, limit=500)
    by_category: dict[str, int] = {}
    for sat in visible:
        sat["category"] = classify_science_category(sat["name"])
        by_category[sat["category"]] = by_category.get(sat["category"], 0) + 1

    return {
        "location": {"lat": lat, "lon": lon},
        "min_elevation_deg": min_elevation_deg,
        "visible_count": len(visible),
        "catalog_size": len(tle_records),
        "by_category": by_category,
        "satellites": visible,
        "source": SCI_SOURCE + " + Skyfield SGP4, computed at request time",
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
        "category": classify_science_category(tle["name"]),
        "window_min": window_min,
        "track": track,
        "source": "CelesTrak science group + Skyfield SGP4, computed at request time",
    }


@router.get("/sky-tracks")
async def sky_tracks(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    min_elevation_deg: float = Query(10, ge=0, le=90),
    elevation_m: float = Query(0),
    window_min: int = Query(25, ge=5, le=90),
):
    tle_records = await _safe_fetch_group_tle()

    visible = compute_visible(tle_records, lat, lon, min_elevation_deg=min_elevation_deg, limit=500)
    visible_norad_ids = {sat["norad_id"] for sat in visible}
    name_by_norad = {sat["norad_id"]: sat["name"] for sat in visible}

    visible_tle_records = [rec for rec in tle_records if _norad_from_tle(rec) in visible_norad_ids]

    tracks = compute_sky_tracks_batch(visible_tle_records, lat, lon, elevation_m, window_min=window_min)
    return {
        "location": {"lat": lat, "lon": lon},
        "window_min": window_min,
        "tracks": {
            str(norad_id): {"category": classify_science_category(name_by_norad.get(norad_id, "")), "points": points}
            for norad_id, points in tracks.items()
        },
        "source": SCI_SOURCE + " + Skyfield SGP4, computed at request time",
    }


# --- Static reference data: general mission-family context, NOT telemetry --
SERVICE_INFO = [
    {
        "category": "Astrophysics & Astronomy", "full_name": "Astrophysics & Astronomy",
        "description": "Space telescopes and observatories that look outward — at stars, galaxies, exoplanets, and high-energy phenomena — from above the distorting effect of Earth's atmosphere.",
        "example_missions": ["Hubble Space Telescope", "Swift Observatory", "NuSTAR", "TESS"],
        "source": "NASA Science", "source_url": "https://science.nasa.gov/astrophysics/",
    },
    {
        "category": "Heliophysics & Space Weather", "full_name": "Heliophysics & Space Weather",
        "description": "Missions studying the Sun, the solar wind, and how solar activity drives space weather that affects satellites, power grids, and astronauts.",
        "example_missions": ["SOHO", "ACE", "DSCOVR", "TIMED"],
        "source": "NASA Heliophysics", "source_url": "https://science.nasa.gov/heliophysics/",
    },
    {
        "category": "Earth & Climate Science", "full_name": "Earth & Climate Science",
        "description": "Satellites measuring ice sheets, sea level, clouds, and the broader climate system — distinct from Portal 02's operational hazard-monitoring satellites.",
        "example_missions": ["ICESat-2", "GRACE-FO", "CALIPSO", "SWOT"],
        "source": "NASA Earth Science", "source_url": "https://science.nasa.gov/earth-science/",
    },
    {
        "category": "Technology Demonstration", "full_name": "Technology Demonstration",
        "description": "Small satellites and university/agency CubeSats flight-testing new instruments, propulsion, or spacecraft techniques ahead of larger missions.",
        "example_missions": ["CUTE", "AAUSAT series", "various PROBA missions"],
        "source": "NASA Small Spacecraft Technology", "source_url": "https://www.nasa.gov/mission/small-spacecraft-technology-program/",
    },
    {
        "category": "Other / Unclassified", "full_name": "Other / Unclassified",
        "description": "Catalogued by CelesTrak under Space & Earth Science but not confidently matched to a family above from its public name alone.",
        "example_missions": [],
        "source": "CelesTrak", "source_url": "https://celestrak.org/",
    },
]


@router.get("/service-info")
def service_info():
    return {
        "categories": SERVICE_INFO,
        "is_static_reference_data": True,
        "note": "General mission-family context from public agency pages — not live telemetry. Live satellite counts and positions come from /overview, /categories and /globe-objects instead.",
    }
