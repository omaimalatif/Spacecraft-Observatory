# Portal 04 — Communication Satellite Systems.
# Source: CelesTrak GP catalog, fetched per named communication group (free,
# no key) — SGP4-propagated server-side with Skyfield, same live-data pattern
# as Portal 03 (Navigation). Unlike GNSS (one bundled CelesTrak group), there
# is no single official "all communications" CelesTrak group, so this router
# fetches each classic operator/constellation group separately and tags every
# object with the exact group it actually came from — a category label is
# never guessed from the satellite's name. Very large broadband mega-
# constellations (Starlink, OneWeb, Kuiper, Qianfan, Guowang — tens of
# thousands of objects combined) are deliberately left out of this curated
# set so the globe/sky-plot stay legible; that omission is disclosed in
# /overview and /service-info rather than silently applied.
from __future__ import annotations

import asyncio
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

# --- Category definitions ----------------------------------------------------
# Each category is backed by exactly one real CelesTrak group. The category
# an object is tagged with reflects which group it was actually fetched from,
# not a name guess.
COMM_GROUPS: dict[str, str] = {
    "Intelsat": "intelsat",
    "SES": "ses",
    "Eutelsat": "eutelsat",
    "Telesat": "telesat",
    "Iridium NEXT": "iridium-NEXT",
    "Orbcomm": "orbcomm",
    "Globalstar": "globalstar",
    "Amateur Radio": "amateur",
}
CATEGORY_ORDER = list(COMM_GROUPS.keys())
COMM_SOURCE = "CelesTrak GP catalog (" + ", ".join(f"GROUP={g}" for g in COMM_GROUPS.values()) + ")"
EXCLUDED_NOTE = (
    "Broadband mega-constellations (Starlink, OneWeb, Kuiper, Qianfan, Guowang) are "
    "excluded from this curated set — tens of thousands of combined objects would "
    "overwhelm the globe and sky plot. Use Portal 01 (Global Space Assets) for those."
)

CATEGORY_META = {
    "Intelsat": {"full_name": "Intelsat", "operator": "Intelsat S.A."},
    "SES": {"full_name": "SES", "operator": "SES S.A."},
    "Eutelsat": {"full_name": "Eutelsat", "operator": "Eutelsat Group"},
    "Telesat": {"full_name": "Telesat", "operator": "Telesat Corporation"},
    "Iridium NEXT": {"full_name": "Iridium NEXT", "operator": "Iridium Communications Inc."},
    "Orbcomm": {"full_name": "Orbcomm", "operator": "ORBCOMM Inc."},
    "Globalstar": {"full_name": "Globalstar", "operator": "Globalstar, Inc."},
    "Amateur Radio": {"full_name": "Amateur Radio Satellites", "operator": "Various (AMSAT and national amateur-radio bodies)"},
}


def _norad_from_tle(rec: dict) -> int | None:
    try:
        return int(rec["line1"][2:7])
    except (ValueError, IndexError, KeyError, TypeError):
        return None


async def _safe_fetch_group_json(group: str) -> list[dict]:
    try:
        return await fetch_group_json(group)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach CelesTrak (GROUP={group}): {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


async def _fetch_all_categories_json() -> list[tuple[str, dict]]:
    """[(category, omm_record), ...] across every comm group, fetched concurrently."""
    results = await asyncio.gather(
        *(_safe_fetch_group_json(group) for group in COMM_GROUPS.values()),
        return_exceptions=True,
    )
    tagged: list[tuple[str, dict]] = []
    seen_norad: set[int] = set()
    for category, result in zip(CATEGORY_ORDER, results):
        if isinstance(result, Exception):
            continue
        for item in result:
            norad = item.get("NORAD_CAT_ID")
            # A satellite can legitimately appear in more than one CelesTrak
            # group; keep its first (highest-priority / CATEGORY_ORDER) tag
            # rather than double-counting it under two categories.
            if norad in seen_norad:
                continue
            seen_norad.add(norad)
            tagged.append((category, item))
    if not tagged:
        raise HTTPException(status_code=502, detail="Could not load communication satellites from CelesTrak")
    return tagged


async def _fetch_all_categories_tle() -> list[tuple[str, dict]]:
    """[(category, {name, line1, line2}), ...] across every comm group, fetched concurrently."""
    results = await asyncio.gather(
        *(fetch_group_tle(group) for group in COMM_GROUPS.values()),
        return_exceptions=True,
    )
    tagged: list[tuple[str, dict]] = []
    seen_norad: set[int] = set()
    for category, result in zip(CATEGORY_ORDER, results):
        if isinstance(result, Exception):
            continue
        for rec in result:
            norad = _norad_from_tle(rec)
            if norad is None or norad in seen_norad:
                continue
            seen_norad.add(norad)
            tagged.append((category, rec))
    if not tagged:
        raise HTTPException(status_code=502, detail="Could not load communication satellite TLEs from CelesTrak")
    return tagged


def _shape_satellite(category: str, item: dict) -> dict:
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
        "category": category,
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


# --- /overview ---------------------------------------------------------------
@router.get("/overview")
async def overview():
    tagged = await _fetch_all_categories_json()
    shaped = [_shape_satellite(category, item) for category, item in tagged]

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
        "source": COMM_SOURCE,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "notes": {
            "categories": "Each category is one real CelesTrak group, tagged by source, not guessed from the satellite name.",
            "excluded": EXCLUDED_NOTE,
        },
    }


# --- /categories (richer payload, kept alongside /overview) -----------------
@router.get("/categories")
async def categories():
    tagged = await _fetch_all_categories_json()
    shaped = [_shape_satellite(category, item) for category, item in tagged]

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
        "source": COMM_SOURCE,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# --- /satellites (search / listing) ------------------------------------------
@router.get("/satellites")
async def satellites(
    category: str | None = Query(None, description="Filter by category, e.g. Intelsat, SES, Iridium NEXT"),
    q: str | None = Query(None, min_length=1, max_length=80, description="Free-text search over satellite name"),
    limit: int = Query(500, le=2000),
):
    tagged = await _fetch_all_categories_json()
    shaped = [_shape_satellite(c, item) for c, item in tagged]

    if category:
        shaped = [s for s in shaped if s["category"].lower() == category.lower()]
    if q:
        needle = q.strip().lower()
        shaped = [s for s in shaped if needle in str(s["name"] or "").lower() or needle in str(s["norad_id"] or "")]

    return {
        "count": len(shaped),
        "satellites": shaped[:limit],
        "source": COMM_SOURCE,
    }


# --- Live 3D globe: SGP4-propagated positions --------------------------------
_globe_cache = TTLCache(maxsize=2, ttl=300)  # 5 min — matches Portal 03's cadence


async def _propagated_comm_objects() -> dict:
    cache_key = "comm_globe"
    if cache_key in _globe_cache:
        return _globe_cache[cache_key]

    tagged_tle = await _fetch_all_categories_tle()
    tle_records = [rec for _category, rec in tagged_tle]
    category_by_norad = {n: c for c, rec in tagged_tle if (n := _norad_from_tle(rec)) is not None}

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
        "source": COMM_SOURCE + ", SGP4-propagated (Skyfield) at request time",
        "count": len(objects),
        "objects": objects,
    }
    _globe_cache[cache_key] = result
    return result


@router.get("/globe-objects")
async def globe_objects():
    try:
        return await _propagated_comm_objects()
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
    cache_key = "comm_orbit_paths"
    if cache_key in _orbit_paths_cache:
        return _orbit_paths_cache[cache_key]

    tagged_tle = await _fetch_all_categories_tle()
    tle_records = [rec for _category, rec in tagged_tle]
    category_by_norad = {n: c for c, rec in tagged_tle if (n := _norad_from_tle(rec)) is not None}

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
        "source": COMM_SOURCE + ", SGP4-propagated (Skyfield) — one full orbital period per satellite",
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
    tagged_tle = await _fetch_all_categories_tle()
    tle_records = [rec for _category, rec in tagged_tle]
    category_by_norad = {n: c for c, rec in tagged_tle if (n := _norad_from_tle(rec)) is not None}

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
        "source": COMM_SOURCE + " + Skyfield SGP4, computed at request time",
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
    tagged_tle = await _fetch_all_categories_tle()
    tle_records = [rec for _category, rec in tagged_tle]
    category_by_norad = {n: c for c, rec in tagged_tle if (n := _norad_from_tle(rec)) is not None}

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
        "source": COMM_SOURCE + " + Skyfield SGP4, computed at request time",
    }


# --- Static reference data: published specifications, NOT live telemetry ----
SERVICE_INFO = [
    {
        "category": "Intelsat", "full_name": "Intelsat",
        "operator": "Intelsat S.A.", "status": "Operational fleet",
        "orbital_regime": "GEO", "altitude_km": 35786, "fleet_size_note": "~50 in-orbit GEO satellites (fleet varies with launches/retirements)",
        "services": ["Broadcast/media distribution", "Fixed satellite service (FSS)", "Government/mobility connectivity"],
        "source": "Intelsat", "source_url": "https://www.intelsat.com/",
    },
    {
        "category": "SES", "full_name": "SES",
        "operator": "SES S.A.", "status": "Operational fleet",
        "orbital_regime": "GEO + MEO", "altitude_km": 35786, "fleet_size_note": "GEO fleet plus the O3b/O3b mPOWER MEO constellation",
        "services": ["Video distribution", "Government connectivity", "MEO broadband (O3b mPOWER)"],
        "source": "SES", "source_url": "https://www.ses.com/",
    },
    {
        "category": "Eutelsat", "full_name": "Eutelsat Group",
        "operator": "Eutelsat Group (merged with OneWeb)", "status": "Operational fleet",
        "orbital_regime": "GEO", "altitude_km": 35786, "fleet_size_note": "GEO broadcast fleet across Europe, Africa, Asia and the Americas",
        "services": ["Broadcast/DTH television", "Data & connectivity", "Government services"],
        "source": "Eutelsat Group", "source_url": "https://eutelsat.com/",
    },
    {
        "category": "Telesat", "full_name": "Telesat",
        "operator": "Telesat Corporation", "status": "Operational fleet",
        "orbital_regime": "GEO", "altitude_km": 35786, "fleet_size_note": "GEO fleet; Telesat Lightspeed LEO constellation in deployment",
        "services": ["Broadcast distribution", "Enterprise/government data", "Maritime & aeronautical connectivity"],
        "source": "Telesat", "source_url": "https://www.telesat.com/",
    },
    {
        "category": "Iridium NEXT", "full_name": "Iridium NEXT",
        "operator": "Iridium Communications Inc.", "status": "Fully operational (66 active + spares)",
        "orbital_regime": "LEO", "altitude_km": 780, "fleet_size_note": "66 operational satellites across 6 polar planes, plus in-orbit spares",
        "services": ["Global voice & low-rate data", "L-band IoT (Iridium Short Burst Data)", "Aireon global air-traffic surveillance hosted payload"],
        "source": "Iridium Communications", "source_url": "https://www.iridium.com/",
    },
    {
        "category": "Orbcomm", "full_name": "Orbcomm",
        "operator": "ORBCOMM Inc.", "status": "Operational",
        "orbital_regime": "LEO", "altitude_km": 715, "fleet_size_note": "Second-generation (OG2) satellite fleet plus legacy satellites",
        "services": ["Machine-to-machine (M2M) / IoT messaging", "Asset tracking", "AIS ship tracking"],
        "source": "ORBCOMM", "source_url": "https://www.orbcomm.com/",
    },
    {
        "category": "Globalstar", "full_name": "Globalstar",
        "operator": "Globalstar, Inc.", "status": "Operational",
        "orbital_regime": "LEO", "altitude_km": 1414, "fleet_size_note": "Second-generation constellation",
        "services": ["Satellite voice & data", "IoT / SPOT & Simplex messaging", "Partner network capacity (e.g. smartphone satellite messaging)"],
        "source": "Globalstar", "source_url": "https://www.globalstar.com/",
    },
    {
        "category": "Amateur Radio", "full_name": "Amateur Radio Satellites",
        "operator": "Various (AMSAT and national amateur-radio organizations)", "status": "Mixed — many active, some defunct but still catalogued",
        "orbital_regime": "Mostly LEO", "altitude_km": 600, "fleet_size_note": "Dozens of small satellites built by universities, AMSAT chapters and hobbyist groups worldwide",
        "services": ["Amateur voice/data repeaters", "APRS digipeating", "Educational technology demonstration"],
        "source": "AMSAT", "source_url": "https://www.amsat.org/",
    },
]


@router.get("/service-info")
def service_info():
    return {
        "categories": SERVICE_INFO,
        "is_static_reference_data": True,
        "excluded_note": EXCLUDED_NOTE,
        "note": "Published fleet/service facts from each operator's own site — not live telemetry. Live satellite counts and positions come from /overview, /categories and /globe-objects instead.",
    }
