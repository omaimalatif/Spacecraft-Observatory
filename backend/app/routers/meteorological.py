# Portal 05 — Meteorological & Environmental Satellites.
# Source: CelesTrak GP catalog, GROUP=weather. Unlike Portal 04 (Communication),
# where each category is its own separate CelesTrak group, CelesTrak bundles
# every weather/environmental satellite into this ONE official group — so the
# group membership itself is authoritative (not guessed), but the family
# labels used for the category breakdown (GOES, Meteosat, Fengyun, etc.) are
# derived by matching each object's name against well-known mission-name
# patterns within that single group. That's a narrower, more honest thing
# than the Portal 04 pattern: it can mislabel an object's family, but it can
# never smuggle a non-weather satellite in, because the upstream group
# membership was never touched.
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

WEATHER_GROUP = "weather"
METEO_SOURCE = "CelesTrak GP catalog (GROUP=weather)"

# --- Family classification (within the single weather group) ----------------
# Checked in order; first match wins. Patterns are literal mission-name
# substrings, not a guess at satellite purpose.
FAMILY_PATTERNS: list[tuple[str, list[str]]] = [
    ("GOES", ["GOES", "EWS-G"]),
    ("Meteosat / MTG", ["METEOSAT", "MTG-"]),
    ("Metop", ["METOP"]),
    ("NOAA POES / JPSS", ["NOAA ", "SUOMI NPP"]),
    ("Fengyun", ["FENGYUN"]),
    ("DMSP", ["DMSP"]),
    ("Roscosmos (Meteor/Elektro/Arktika)", ["METEOR-M", "ELEKTRO-L", "ARKTIKA-M"]),
]
CATEGORY_ORDER = [c for c, _ in FAMILY_PATTERNS] + ["Other"]

CATEGORY_META = {
    "GOES": {"full_name": "GOES", "operator": "NOAA / NASA"},
    "Meteosat / MTG": {"full_name": "Meteosat / Meteosat Third Generation", "operator": "EUMETSAT"},
    "Metop": {"full_name": "Metop", "operator": "EUMETSAT"},
    "NOAA POES / JPSS": {"full_name": "NOAA POES / JPSS", "operator": "NOAA / NASA"},
    "Fengyun": {"full_name": "Fengyun", "operator": "China Meteorological Administration (CMA)"},
    "DMSP": {"full_name": "Defense Meteorological Satellite Program", "operator": "U.S. Space Force"},
    "Roscosmos (Meteor/Elektro/Arktika)": {"full_name": "Meteor-M / Elektro-L / Arktika-M", "operator": "Roscosmos"},
    "Other": {"full_name": "Other weather & environmental satellites", "operator": "Various (JMA, ISRO, KMA, ESA/EUMETSAT, NASA, commercial)"},
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


async def _fetch_weather_json() -> list[dict]:
    try:
        return await fetch_group_json(WEATHER_GROUP)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach CelesTrak: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


async def _fetch_weather_tle() -> list[dict]:
    try:
        return await fetch_group_tle(WEATHER_GROUP)
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


# --- /overview ---------------------------------------------------------------
@router.get("/overview")
async def overview():
    items = await _fetch_weather_json()
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
        "source": METEO_SOURCE,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "notes": {
            "categories": "Group membership (weather) is CelesTrak's own official grouping. Family labels (GOES, Meteosat, Fengyun, etc.) within that group are derived from name-pattern matching, not upstream metadata.",
        },
    }


# --- /categories (richer payload, kept alongside /overview) -----------------
@router.get("/categories")
async def categories():
    items = await _fetch_weather_json()
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
        "source": METEO_SOURCE,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# --- /satellites (search / listing) ------------------------------------------
@router.get("/satellites")
async def satellites(
    category: str | None = Query(None, description="Filter by category, e.g. GOES, Meteosat / MTG, Fengyun"),
    q: str | None = Query(None, min_length=1, max_length=80, description="Free-text search over satellite name"),
    limit: int = Query(500, le=2000),
):
    items = await _fetch_weather_json()
    shaped = [_shape_satellite(item) for item in items]

    if category:
        shaped = [s for s in shaped if s["category"].lower() == category.lower()]
    if q:
        needle = q.strip().lower()
        shaped = [s for s in shaped if needle in str(s["name"] or "").lower() or needle in str(s["norad_id"] or "")]

    return {
        "count": len(shaped),
        "satellites": shaped[:limit],
        "source": METEO_SOURCE,
    }


# --- Live 3D globe: SGP4-propagated positions --------------------------------
_globe_cache = TTLCache(maxsize=2, ttl=300)  # 5 min — matches Portals 03/04's cadence


async def _propagated_meteo_objects() -> dict:
    cache_key = "meteo_globe"
    if cache_key in _globe_cache:
        return _globe_cache[cache_key]

    tle_records = await _fetch_weather_tle()
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
        "source": METEO_SOURCE + ", SGP4-propagated (Skyfield) at request time",
        "count": len(objects),
        "objects": objects,
    }
    _globe_cache[cache_key] = result
    return result


@router.get("/globe-objects")
async def globe_objects():
    try:
        return await _propagated_meteo_objects()
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
    cache_key = "meteo_orbit_paths"
    if cache_key in _orbit_paths_cache:
        return _orbit_paths_cache[cache_key]

    tle_records = await _fetch_weather_tle()
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
        "source": METEO_SOURCE + ", SGP4-propagated (Skyfield) — one full orbital period per satellite",
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
    tle_records = await _fetch_weather_tle()
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
        "source": METEO_SOURCE + " + Skyfield SGP4, computed at request time",
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
    tle_records = await _fetch_weather_tle()
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
        "source": METEO_SOURCE + " + Skyfield SGP4, computed at request time",
    }


# --- Static reference data: published specifications, NOT live telemetry ----
SERVICE_INFO = [
    {
        "category": "GOES", "full_name": "GOES (Geostationary Operational Environmental Satellite)",
        "operator": "NOAA / NASA", "status": "Operational (GOES-16 East, GOES-18 West; GOES-19 phasing in)",
        "orbital_regime": "GEO", "altitude_km": 35786, "fleet_size_note": "2 primary operational + 1-2 on-orbit spares",
        "services": ["Real-time storm/hurricane imagery (ABI)", "Lightning mapping (GLM)", "Space weather monitoring"],
        "source": "NOAA NESDIS", "source_url": "https://www.goes.noaa.gov/",
    },
    {
        "category": "Meteosat / MTG", "full_name": "Meteosat / Meteosat Third Generation",
        "operator": "EUMETSAT", "status": "Operational (MSG series + first MTG-I satellite)",
        "orbital_regime": "GEO", "altitude_km": 35786, "fleet_size_note": "Multiple in-orbit satellites covering Europe, Africa and the Indian Ocean",
        "services": ["Full-disk imagery for Europe/Africa", "Severe weather nowcasting", "Lightning imaging (MTG)"],
        "source": "EUMETSAT", "source_url": "https://www.eumetsat.int/",
    },
    {
        "category": "Metop", "full_name": "Metop",
        "operator": "EUMETSAT", "status": "Operational polar-orbiting fleet",
        "orbital_regime": "LEO (sun-synchronous)", "altitude_km": 817, "fleet_size_note": "Metop-B and Metop-C operational; part of the joint EUMETSAT/NOAA polar system",
        "services": ["Global atmospheric sounding", "Ocean surface wind (scatterometer)", "Numerical weather prediction input"],
        "source": "EUMETSAT", "source_url": "https://www.eumetsat.int/metop",
    },
    {
        "category": "NOAA POES / JPSS", "full_name": "NOAA POES / Joint Polar Satellite System",
        "operator": "NOAA / NASA", "status": "Operational (Suomi NPP, NOAA-20, NOAA-21)",
        "orbital_regime": "LEO (sun-synchronous)", "altitude_km": 824, "fleet_size_note": "Multiple polar-orbiting satellites in complementary orbits",
        "services": ["Global imagery & sounding (VIIRS, CrIS, ATMS)", "Climate data records", "Search-and-rescue relay (SARSAT)"],
        "source": "NOAA NESDIS", "source_url": "https://www.nesdis.noaa.gov/jpss",
    },
    {
        "category": "Fengyun", "full_name": "Fengyun",
        "operator": "China Meteorological Administration (CMA)", "status": "Operational (FY-2/FY-4 geostationary, FY-3 polar)",
        "orbital_regime": "GEO + LEO", "altitude_km": 35786, "fleet_size_note": "Mixed geostationary and polar-orbiting fleet",
        "services": ["Regional weather imagery (East Asia/Pacific)", "Polar atmospheric sounding", "Space & environmental monitoring"],
        "source": "China Meteorological Administration", "source_url": "https://www.cma.gov.cn/",
    },
    {
        "category": "DMSP", "full_name": "Defense Meteorological Satellite Program",
        "operator": "U.S. Space Force", "status": "Legacy — remaining satellites well past design life",
        "orbital_regime": "LEO (sun-synchronous)", "altitude_km": 830, "fleet_size_note": "A handful of aging satellites (F16-F18) still catalogued and occasionally used",
        "services": ["Cloud imagery", "Special sensor microwave sounding", "Auroral/space-environment monitoring"],
        "source": "U.S. Space Force / NOAA (data archive)", "source_url": "https://www.ospo.noaa.gov/Operations/DMSP/",
    },
    {
        "category": "Roscosmos (Meteor/Elektro/Arktika)", "full_name": "Meteor-M / Elektro-L / Arktika-M",
        "operator": "Roscosmos", "status": "Operational",
        "orbital_regime": "LEO + GEO + HEO (Molniya-type for Arktika-M)", "altitude_km": 35786, "fleet_size_note": "Meteor-M (polar), Elektro-L (GEO), Arktika-M (highly elliptical, Arctic coverage)",
        "services": ["Polar & geostationary weather imagery", "Arctic-region monitoring (Arktika-M's specialty)", "Space environment monitoring"],
        "source": "Roshydromet / Roscosmos", "source_url": "https://planet.rssi.ru/",
    },
]

METEO_OTHER_NOTE = (
    "The 'Other' category groups additional weather & environmental missions inside CelesTrak's weather "
    "group that don't match one of the named families above — regional geostationary satellites "
    "(INSAT, Himawari, COMS, GEO-KOMPSAT), ocean/atmosphere research missions (Sentinel-3), and "
    "commercial GNSS radio-occultation constellations (CYGNSS, Tianmu-1) that CelesTrak also files under weather."
)


@router.get("/service-info")
def service_info():
    return {
        "categories": SERVICE_INFO,
        "is_static_reference_data": True,
        "excluded_note": METEO_OTHER_NOTE,
        "note": "Published fleet/service facts from each operator's own site — not live telemetry. Live satellite counts and positions come from /overview, /categories and /globe-objects instead.",
    }
