# Portal 03 — Navigation Satellite Systems (GNSS).
# Source: CelesTrak GP catalog, GROUP=gnss (free, no key) — SGP4-propagated
# server-side with Skyfield for live positions and visibility, same pattern
# as Portal 01. Where CelesTrak's GP feed simply doesn't carry a field (a
# ground-station network, live signal-in-space health, real accuracy
# telemetry) this file says so instead of inventing it — the /service-info
# endpoint is explicitly labelled as static published reference data, not
# live telemetry, and is sourced to each constellation's own ICD/authority.
from __future__ import annotations

from datetime import datetime, timezone

import httpx
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException, Query

from app.services.celestrak import fetch_group_json, fetch_group_tle, fetch_object_tle
from app.services.orbital import (
    compute_orbit_path,
    compute_orbit_paths_batch,
    compute_sky_track,
    compute_sky_tracks_batch,
    compute_visible,
    propagate_subpoints,
)

router = APIRouter()

GNSS_SOURCE = "CelesTrak GP catalog (GROUP=gnss)"

# --- Constellation classification -------------------------------------------
# CelesTrak's `gnss` group bundles the six core GNSS constellations together
# with SBAS/augmentation payloads that ride on communications satellites
# (WAAS, EGNOS, GAGAN, SDCM, MSAS) — those are real navigation-relevant
# objects but are not one of the "6 GNSS constellations" the portal counts,
# so they're kept in their own bucket rather than folded into a core system
# or silently dropped. Classification is by CelesTrak OBJECT_NAME prefix —
# the same naming convention CelesTrak itself publishes, not guessed.
CORE_CONSTELLATIONS = ["GPS", "GLONASS", "Galileo", "BeiDou", "QZSS", "NavIC"]

CONSTELLATION_META = {
    "GPS": {"full_name": "Global Positioning System", "operator": "United States (US Space Force)"},
    "GLONASS": {"full_name": "Global'naya Navigatsionnaya Sputnikovaya Sistema", "operator": "Russia (Roscosmos)"},
    "Galileo": {"full_name": "Galileo", "operator": "European Union (EUSPA)"},
    "BeiDou": {"full_name": "BeiDou Navigation Satellite System", "operator": "China (CSNO)"},
    "QZSS": {"full_name": "Quasi-Zenith Satellite System", "operator": "Japan (Cabinet Office / QZSS)"},
    "NavIC": {"full_name": "Navigation with Indian Constellation", "operator": "India (ISRO)"},
    "SBAS": {"full_name": "Satellite-Based Augmentation Systems", "operator": "Multiple (WAAS/EGNOS/GAGAN/SDCM/MSAS)"},
    "Other": {"full_name": "Unclassified navigation-group object", "operator": "Unknown"},
}


def classify_constellation(name: str) -> str:
    n = (name or "").upper().strip()
    if n.startswith("GPS"):
        return "GPS"
    if n.startswith("GSAT0") or "GALILEO" in n:
        return "Galileo"
    if n.startswith("BEIDOU"):
        return "BeiDou"
    if n.startswith("QZS"):
        return "QZSS"
    if n.startswith("IRNSS") or n.startswith("NVS") or "IRNSS" in n:
        return "NavIC"
    if any(tag in n for tag in ("WAAS", "EGNOS", "GAGAN", "SDCM", "MSAS")):
        return "SBAS"
    if n.startswith("COSMOS"):
        return "GLONASS"
    if any(tag in n for tag in ("INMARSAT", "SES-", "GALAXY", "EUTELSAT", "ASTRA", "LUCH", "GSAT-")):
        return "SBAS"
    return "Other"


def classify_nav_regime(mean_motion, inclination) -> str:
    """GNSS-specific regime split: the shared classify_regime() elsewhere in
    this backend is tuned for the whole-catalog LEO/MEO/GEO/HEO split and
    mis-buckets true GEO (period ~1436 min) as HEO — fine for Portal 01's
    long tail of objects, wrong for a portal where GEO/IGSO satellites are
    the norm. This version uses period + inclination, which is what actually
    distinguishes GEO from IGSO at the same period."""
    if not mean_motion:
        return "UNKNOWN"
    period_min = 1440 / mean_motion
    if period_min < 300:
        return "LEO"
    if period_min <= 1000:
        return "MEO"
    if 1300 <= period_min <= 1500:
        if inclination is not None and inclination < 5:
            return "GEO"
        return "IGSO"
    return "OTHER"


async def _safe_fetch_group_json(group: str) -> list[dict]:
    try:
        return await fetch_group_json(group)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach CelesTrak (GROUP={group}): {exc}") from exc
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
        "constellation": classify_constellation(name),
        "regime": classify_nav_regime(mean_motion, inclination),
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
    """Single round-trip KPI + breakdown payload for the Navigation dashboard header."""
    data = await _safe_fetch_group_json("gnss")
    shaped = [_shape_satellite(item) for item in data]

    by_constellation: dict[str, int] = {}
    by_regime: dict[str, int] = {}
    for sat in shaped:
        by_constellation[sat["constellation"]] = by_constellation.get(sat["constellation"], 0) + 1
        by_regime[sat["regime"]] = by_regime.get(sat["regime"], 0) + 1

    core_active = [c for c in CORE_CONSTELLATIONS if by_constellation.get(c, 0) > 0]

    return {
        "total_satellites": len(shaped),
        "core_constellation_count": len(core_active),
        "core_constellations": core_active,
        "by_constellation": by_constellation,
        "by_regime": by_regime,
        "source": GNSS_SOURCE,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "notes": {
            "core_constellation_count": "Core GNSS systems with at least one currently-catalogued satellite in this feed (GPS, GLONASS, Galileo, BeiDou, QZSS, NavIC).",
            "by_constellation": "SBAS/Other = augmentation or unclassified objects riding in CelesTrak's gnss group; not one of the 6 core constellations.",
            "by_regime": "GEO/IGSO split uses period + inclination, not CelesTrak's raw fields (CelesTrak does not label this directly).",
        },
    }


# --- /constellations (kept for backward compatibility, richer payload) ------
@router.get("/constellations")
async def constellations():
    data = await _safe_fetch_group_json("gnss")
    shaped = [_shape_satellite(item) for item in data]

    groups: dict[str, dict] = {}
    for sat in shaped:
        key = sat["constellation"]
        entry = groups.setdefault(key, {
            "constellation": key,
            **CONSTELLATION_META.get(key, CONSTELLATION_META["Other"]),
            "satellite_count": 0,
            "by_regime": {},
        })
        entry["satellite_count"] += 1
        entry["by_regime"][sat["regime"]] = entry["by_regime"].get(sat["regime"], 0) + 1

    ordered = [groups[c] for c in CORE_CONSTELLATIONS if c in groups]
    ordered += [groups[c] for c in groups if c not in CORE_CONSTELLATIONS]

    return {
        "total": len(shaped),
        "constellations": ordered,
        "source": GNSS_SOURCE,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# --- /satellites (search / listing) ------------------------------------------
@router.get("/satellites")
async def satellites(
    constellation: str | None = Query(None, description="Filter by constellation, e.g. GPS, Galileo, BeiDou"),
    q: str | None = Query(None, min_length=1, max_length=80, description="Free-text search over satellite name"),
    limit: int = Query(500, le=2000),
):
    data = await _safe_fetch_group_json("gnss")
    shaped = [_shape_satellite(item) for item in data]

    if constellation:
        shaped = [s for s in shaped if s["constellation"].lower() == constellation.lower()]
    if q:
        needle = q.strip().lower()
        shaped = [s for s in shaped if needle in str(s["name"] or "").lower() or needle in str(s["norad_id"] or "")]

    return {
        "count": len(shaped),
        "satellites": shaped[:limit],
        "source": GNSS_SOURCE,
    }


# --- Live 3D globe: SGP4-propagated GNSS positions ---------------------------
_globe_cache = TTLCache(maxsize=2, ttl=300)  # 5 min — matches Portal 01's cadence


async def _propagated_gnss_objects() -> dict:
    cache_key = "gnss_globe"
    if cache_key in _globe_cache:
        return _globe_cache[cache_key]

    tle_records = await fetch_group_tle("gnss")
    positions = propagate_subpoints(tle_records)

    by_norad_tle = {}
    for rec in tle_records:
        try:
            norad_id = int(rec["line1"][2:7])
        except (ValueError, IndexError, KeyError):
            continue
        by_norad_tle[norad_id] = rec

    objects = []
    for norad_id, pos in positions.items():
        rec = by_norad_tle.get(norad_id)
        if not rec:
            continue
        constellation = classify_constellation(rec["name"])
        regime = classify_nav_regime(pos.get("mean_motion"), pos.get("inclination_deg"))
        objects.append({
            "norad_id": norad_id,
            "name": rec["name"],
            "constellation": constellation,
            "regime": regime,
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
        "source": "CelesTrak GNSS group, SGP4-propagated (Skyfield) at request time",
        "count": len(objects),
        "objects": objects,
    }
    _globe_cache[cache_key] = result
    return result


@router.get("/globe-objects")
async def globe_objects():
    """Live SGP4-propagated positions for every GNSS-group satellite, for the 3D globe."""
    try:
        return await _propagated_gnss_objects()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach CelesTrak: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/orbit-path/{norad_id}")
async def orbit_path(norad_id: int):
    """One full orbital period of ground-track points for a single GNSS satellite."""
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
        "constellation": classify_constellation(tle["name"]),
        "source": "CelesTrak GNSS group, SGP4-propagated",
        "path": path,
    }


_orbit_paths_cache = TTLCache(maxsize=2, ttl=300)  # 5 min, same cadence as /globe-objects


@router.get("/orbit-paths")
async def orbit_paths():
    """
    Real SGP4-propagated orbit trajectory for every GNSS-group satellite at
    once, each sampled across its own orbital period — this is what draws
    the constellation-colored 3D orbit lines on the globe (replacing any
    single hardcoded/manual ellipse) without issuing one request per
    satellite.
    """
    cache_key = "gnss_orbit_paths"
    if cache_key in _orbit_paths_cache:
        return _orbit_paths_cache[cache_key]

    try:
        tle_records = await fetch_group_tle("gnss")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach CelesTrak: {exc}") from exc

    by_norad_tle = {}
    for rec in tle_records:
        try:
            norad_id = int(rec["line1"][2:7])
        except (ValueError, IndexError, KeyError):
            continue
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
            "constellation": classify_constellation(rec["name"]),
            "period_min": entry["period_min"],
            "path": entry["path"],
        })

    result = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "source": "CelesTrak GNSS group, SGP4-propagated (Skyfield) — one full orbital period per satellite",
        "count": len(objects),
        "objects": objects,
    }
    _orbit_paths_cache[cache_key] = result
    return result


# --- Regional availability: real elevation-based visibility, not a heatmap --
# A true per-pixel signal-coverage heatmap needs signal-in-space power and
# receiver-sensitivity modelling that no free feed publishes; what CAN be
# computed honestly from CelesTrak + SGP4 is how many GNSS satellites are
# actually above the horizon (elevation-limited) from a given point right
# now — a real, live availability figure, just not a full heatmap.
@router.get("/availability")
async def availability(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    min_elevation_deg: float = Query(10, ge=0, le=90),
):
    try:
        tle_records = await fetch_group_tle("gnss")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach CelesTrak: {exc}") from exc

    visible = compute_visible(tle_records, lat, lon, min_elevation_deg=min_elevation_deg, limit=500)
    by_constellation: dict[str, int] = {}
    for sat in visible:
        sat["constellation"] = classify_constellation(sat["name"])
        by_constellation[sat["constellation"]] = by_constellation.get(sat["constellation"], 0) + 1

    return {
        "location": {"lat": lat, "lon": lon},
        "min_elevation_deg": min_elevation_deg,
        "visible_count": len(visible),
        "catalog_size": len(tle_records),
        "by_constellation": by_constellation,
        "satellites": visible,
        "source": "CelesTrak GNSS group + Skyfield SGP4, computed at request time",
    }


@router.get("/sky-track/{norad_id}")
async def sky_track(
    norad_id: int,
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    elevation_m: float = Query(0),
    window_min: int = Query(60, ge=5, le=180),
):
    """Real azimuth/elevation track for one satellite across a time window,
    as seen from a ground point — feeds the Sky Plot's Orbits overlay."""
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
        "constellation": classify_constellation(tle["name"]),
        "window_min": window_min,
        "track": track,
        "source": "CelesTrak GNSS group + Skyfield SGP4, computed at request time",
    }


# --- Static reference data: published specifications, NOT live telemetry ----
# These figures (signal counts, orbital altitude bands, stated accuracy) come
# from each system's own published interface/control documents and public
# status pages, not from CelesTrak or any live feed. They change rarely and
# are labelled clearly in the payload so the frontend never presents them as
# real-time. Numbers reflect the operational baseline each authority
# publishes; exact accuracy varies by receiver, augmentation, and region.
SERVICE_INFO = [
    {
        "constellation": "GPS", "full_name": "Global Positioning System",
        "operator": "United States Space Force", "status": "Fully operational",
        "orbital_regime": "MEO", "altitude_km": 20200, "orbital_planes": 6,
        "signals": ["L1 C/A", "L1C", "L2C", "L5"],
        "stated_accuracy": "Better than 7.6 m horizontal (95%), published global average",
        "source": "gps.gov", "source_url": "https://www.gps.gov/systems/gps/performance/accuracy/",
    },
    {
        "constellation": "GLONASS", "full_name": "Global'naya Navigatsionnaya Sputnikovaya Sistema",
        "operator": "Russia — Roscosmos", "status": "Fully operational",
        "orbital_regime": "MEO", "altitude_km": 19100, "orbital_planes": 3,
        "signals": ["L1OF", "L2OF", "L3OC"],
        "stated_accuracy": "~5 m horizontal, published system accuracy",
        "source": "GLONASS ICD (Roscosmos / IAC)", "source_url": "https://www.glonass-iac.ru/en/",
    },
    {
        "constellation": "Galileo", "full_name": "Galileo",
        "operator": "European Union — EUSPA", "status": "Full operational capability",
        "orbital_regime": "MEO", "altitude_km": 23222, "orbital_planes": 3,
        "signals": ["E1", "E5a", "E5b", "E6"],
        "stated_accuracy": "~1 m horizontal (High Accuracy Service), <1 m dual-frequency",
        "source": "European GNSS Service Centre", "source_url": "https://www.gsc-europa.eu/",
    },
    {
        "constellation": "BeiDou", "full_name": "BeiDou Navigation Satellite System (BDS-3)",
        "operator": "China — CSNO", "status": "Fully operational (global, since 2020)",
        "orbital_regime": "MEO / IGSO / GEO", "altitude_km": 21500, "orbital_planes": 3,
        "signals": ["B1I", "B1C", "B2a", "B2b", "B3I"],
        "stated_accuracy": "2.5–5 m horizontal, published global service accuracy",
        "source": "BeiDou ICD (CSNO)", "source_url": "http://www.beidou.gov.cn/",
    },
    {
        "constellation": "QZSS", "full_name": "Quasi-Zenith Satellite System (Michibiki)",
        "operator": "Japan — Cabinet Office", "status": "Operational (regional, Asia-Oceania)",
        "orbital_regime": "IGSO / GEO", "altitude_km": 32000, "orbital_planes": 1,
        "signals": ["L1 C/A", "L1C", "L2C", "L5", "L6"],
        "stated_accuracy": "Sub-metre with augmentation (CLAS), regional service",
        "source": "QZSS official site (Cabinet Office)", "source_url": "https://qzss.go.jp/en/",
    },
    {
        "constellation": "NavIC", "full_name": "Navigation with Indian Constellation (IRNSS)",
        "operator": "India — ISRO", "status": "Operational (regional, India + ~1500 km beyond borders)",
        "orbital_regime": "IGSO / GEO", "altitude_km": 36000, "orbital_planes": 1,
        "signals": ["L5", "S-band", "L1 (newer satellites)"],
        "stated_accuracy": "~10–20 m (SPS), better with dual-frequency",
        "source": "ISRO NavIC programme page", "source_url": "https://www.isro.gov.in/NavIC.html",
    },
    {
        "constellation": "SBAS", "full_name": "Satellite-Based Augmentation Systems",
        "operator": "Multiple regional providers (WAAS / EGNOS / GAGAN / MSAS)", "status": "Operational (regional services)",
        "orbital_regime": "GEO", "altitude_km": 35786, "orbital_planes": "Multiple",
        "signals": ["L1", "L5", "Correction messages"],
        "stated_accuracy": "Typically 1–3 m horizontal with integrity monitoring",
        "source": "European Commission SBAS overview", "source_url": "https://defence-industry-space.ec.europa.eu/eu-space-programme/egnos_en",
    },
]


@router.get("/sky-tracks")
async def sky_tracks(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    min_elevation_deg: float = Query(10, ge=0, le=90),
    elevation_m: float = Query(0),
    window_min: int = Query(25, ge=5, le=90),
):
    """Real azimuth/elevation tracks for EVERY currently-visible GNSS
    satellite at once, as seen from a ground point — feeds the sky dome's
    Orbits overlay so every plotted satellite gets its short orbit arc, not
    just a clicked one. One shared SGP4 batch computation, not N requests."""
    try:
        tle_records = await fetch_group_tle("gnss")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach CelesTrak: {exc}") from exc

    visible = compute_visible(tle_records, lat, lon, min_elevation_deg=min_elevation_deg, limit=500)
    visible_norad_ids = {sat["norad_id"] for sat in visible}
    name_by_norad = {sat["norad_id"]: sat["name"] for sat in visible}

    visible_tle_records = []
    for rec in tle_records:
        try:
            norad_id = int(rec["line1"][2:7])
        except (ValueError, IndexError, KeyError):
            continue
        if norad_id in visible_norad_ids:
            visible_tle_records.append(rec)

    tracks = compute_sky_tracks_batch(visible_tle_records, lat, lon, elevation_m, window_min=window_min)
    return {
        "location": {"lat": lat, "lon": lon},
        "window_min": window_min,
        "tracks": {
            str(norad_id): {"constellation": classify_constellation(name_by_norad.get(norad_id, "")), "points": points}
            for norad_id, points in tracks.items()
        },
        "source": "CelesTrak GNSS group + Skyfield SGP4, computed at request time",
    }


@router.get("/service-info")
def service_info():
    return {
        "constellations": SERVICE_INFO,
        "is_static_reference_data": True,
        "note": "Published specifications from each constellation's own authority — not live telemetry. Live satellite counts and positions come from /overview, /constellations and /globe-objects instead.",
    }
