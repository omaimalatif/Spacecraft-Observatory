# Portal 01 — Global Space Assets
import asyncio
import logging
from datetime import datetime, timezone

import httpx
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException, Query
from app.services.celestrak import (
    fetch_group_json,
    fetch_group_tle,
    fetch_object_tle,
    get_catalog_status,
    search_active_catalog,
    shape_object_minimal,
)
from app.services.orbital import classify_regime, compute_orbit_path, propagate_subpoints
from app.services.satcat import fetch_onorbit as fetch_satcat_onorbit
from app.services.satcat_taxonomy import (
    altitude_bin,
    altitude_bin_labels,
    classify_ops_status,
    classify_regime as classify_regime_satcat,
    owner_display_name,
)

router = APIRouter()
logger = logging.getLogger(__name__)
SATCAT_SOURCE = "CelesTrak SATCAT (celestrak.org/satcat)"


async def _safe_fetch_group(group: str) -> list[dict]:
    """Wraps fetch_group_json so an upstream hiccup returns a clean 502
    instead of an unhandled 500 — an unhandled exception here skips
    CORSMiddleware's response headers, which shows up in the browser as a
    blocked/CORS-looking failure even though the real cause is upstream."""
    try:
        return await fetch_group_json(group)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach CelesTrak (GROUP={group}): {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _satcat_active_payloads(records: list[dict]) -> list[dict]:
    """Adapt active SATCAT payloads to the small catalog shape used by the UI.

    SATCAT has no TLE, so these records are inventory/search fallbacks only;
    they must not be passed to SGP4 propagation endpoints.
    """
    active = []
    for record in records:
        if (record.get("OBJECT_TYPE") or "").upper() != "PAYLOAD":
            continue
        if classify_ops_status(record.get("OPS_STATUS_CODE")) != "active":
            continue
        active.append({
            "OBJECT_NAME": record.get("OBJECT_NAME"),
            "NORAD_CAT_ID": record.get("NORAD_CAT_ID"),
            "OBJECT_ID": record.get("OBJECT_ID"),
            "EPOCH": None,
            "MEAN_MOTION": None,
            "INCLINATION": record.get("INCLINATION"),
            "ECCENTRICITY": None,
        })
    return active


async def _fetch_active_with_fallback() -> tuple[list[dict], str]:
    try:
        return await fetch_group_json("active"), "CelesTrak GP"
    except Exception as exc:
        satcat = await _safe_fetch_satcat_onorbit()
        if satcat is None:
            raise HTTPException(
                status_code=502,
                detail=f"Could not reach CelesTrak GP or SATCAT: {exc}",
            ) from exc
        logger.warning("CelesTrak GP active feed unavailable; using SATCAT fallback")
        return _satcat_active_payloads(satcat), SATCAT_SOURCE


async def _fetch_recent_or_empty() -> list[dict]:
    try:
        return await fetch_group_json("last-30-days")
    except Exception:
        return []


async def _safe_fetch_satcat_onorbit() -> list[dict] | None:
    """Soft-fail SATCAT fetch for endpoints (like /summary) that should
    still return their GP-based fields even if SATCAT is temporarily down —
    partial data beats a hard failure for a dashboard KPI strip."""
    try:
        return await fetch_satcat_onorbit()
    except Exception:
        return None


async def _require_satcat_onorbit() -> list[dict]:
    """Hard-fail version for endpoints (like /by-country) that are
    structurally meaningless without SATCAT — a clean 502 beats a
    misleadingly-empty 200."""
    try:
        return await fetch_satcat_onorbit()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach CelesTrak SATCAT: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _build_summary(active: list[dict], recent: list[dict], onorbit_satcat: list[dict] | None, active_source: str) -> dict:
    regime_counts = {"LEO": 0, "MEO": 0, "GEO": 0, "HEO": 0, "UNKNOWN": 0}
    for sat in active:
        regime_counts[classify_regime(sat.get("MEAN_MOTION"))] += 1

    summary = {
        "total_active": len(active),
        "active_source": active_source,
        "debris": None,
        "rocket_bodies": None,
        "recently_added": len(recent),
        "inactive": None,
        "total_catalogued": None,
        "countries": None,
        "by_regime": regime_counts,
        "source": f"{active_source} (active payloads) + CelesTrak SATCAT (full catalog, type/status/owner)",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "notes": {
            "total_catalogued": "SATCAT temporarily unavailable — showing active inventory only.",
            "inactive": "SATCAT temporarily unavailable.",
            "countries": "SATCAT temporarily unavailable.",
            "debris": "SATCAT temporarily unavailable.",
            "rocket_bodies": "SATCAT temporarily unavailable.",
        },
    }

    if onorbit_satcat is None:
        return summary

    inactive = rocket_bodies = debris = unknown_type = unknown_status = 0
    owners: set[str] = set()
    for rec in onorbit_satcat:
        obj_type = (rec.get("OBJECT_TYPE") or "").upper()
        owner = rec.get("OWNER")
        if owner:
            owners.add(owner.strip())
        if obj_type == "PAYLOAD":
            status = classify_ops_status(rec.get("OPS_STATUS_CODE"))
            if status == "inactive":
                inactive += 1
            elif status == "unknown":
                unknown_status += 1
        elif obj_type == "ROCKET BODY":
            rocket_bodies += 1
        elif obj_type == "DEBRIS":
            debris += 1
        else:
            unknown_type += 1

    summary.update({
        "total_catalogued": len(onorbit_satcat),
        "inactive": inactive,
        "rocket_bodies": rocket_bodies,
        "debris": debris,
        "countries": len(owners),
        "notes": {
            "total_catalogued": f"Source: {SATCAT_SOURCE} (all on-orbit objects).",
            "inactive": f"Source: {SATCAT_SOURCE}. {unknown_status} payloads have an unresolvable status code and are excluded (not guessed).",
            "countries": f"Source: {SATCAT_SOURCE} OWNER field — ownership, not launch site or operator (kept separate, see /by-country).",
            "debris": f"Source: {SATCAT_SOURCE}.",
            "rocket_bodies": f"Source: {SATCAT_SOURCE}. {unknown_type} on-orbit objects have an unresolvable OBJECT_TYPE and are excluded.",
        },
    })
    return summary


@router.get("/dashboard")
async def dashboard():
    """
    Single round-trip payload for Portal 01.
    Fetches the active catalog once and derives summary stats + object list
    together, avoiding duplicate CelesTrak downloads that trigger 403 freezes.
    """
    active_with_source, recent, onorbit_satcat = await asyncio.gather(
        _fetch_active_with_fallback(),
        _fetch_recent_or_empty(),
        _safe_fetch_satcat_onorbit(),
    )
    active, active_source = active_with_source
    return {
        "summary": _build_summary(active, recent, onorbit_satcat, active_source),
        "group": "active",
        "count": len(active),
        "objects": [shape_object_minimal(item) for item in active],
        "catalog_status": get_catalog_status("active"),
    }


@router.get("/summary")
async def summary():
    """Live, source-separated Portal 01 indicators from CelesTrak GP + SATCAT feeds."""
    active_with_source, recent, onorbit_satcat = await asyncio.gather(
        _fetch_active_with_fallback(),
        _fetch_recent_or_empty(),
        _safe_fetch_satcat_onorbit(),
    )
    active, active_source = active_with_source
    return _build_summary(active, recent, onorbit_satcat, active_source)


@router.get("/objects")
async def objects(
    group: str = Query("active", description="CelesTrak group name, e.g. active, stations, gnss"),
    minimal: bool = Query(True, description="Return only UI-relevant OMM fields"),
):
    """Raw OMM object records for any CelesTrak group, passthrough with light shaping."""
    if group.lower() == "active":
        data, source = await _fetch_active_with_fallback()
    else:
        data = await _safe_fetch_group(group)
        source = "CelesTrak GP"
    payload = [shape_object_minimal(item) for item in data] if minimal else data
    return {"group": group, "count": len(payload), "objects": payload, "source": source}


@router.get("/search")
async def search(q: str = Query(..., min_length=1, max_length=80)):
    """Search active payloads, falling back to SATCAT when GP is unavailable."""
    try:
        active, source = await _fetch_active_with_fallback()
    except HTTPException:
        active, source = [], "CelesTrak GP"

    needle = q.strip().lower()
    if source == SATCAT_SOURCE:
        matches = [
            shape_object_minimal(item)
            for item in active
            if needle in str(item.get("OBJECT_NAME") or "").lower()
            or needle in str(item.get("NORAD_CAT_ID") or "").lower()
            or needle in str(item.get("OBJECT_ID") or "").lower()
        ][:25]
    else:
        matches = [shape_object_minimal(item) for item in search_active_catalog(q)]
    return {
        "query": q,
        "count": len(matches),
        "objects": matches,
        "source": f"{source} catalog (active payloads, cached server-side)",
    }


@router.get("/by-country")
async def by_country():
    """
    Real country/entity breakdown from SATCAT's OWNER field — who owns each
    on-orbit object. NOT the same as who launched it or who operates it day
    to day; SATCAT doesn't separate those three, so this only reports what
    it actually has: ownership.
    """
    onorbit = await _require_satcat_onorbit()

    by_owner: dict[str, dict] = {}
    for rec in onorbit:
        code = (rec.get("OWNER") or "UNKNOWN").strip()
        entry = by_owner.setdefault(
            code,
            {"owner_code": code, "owner_name": owner_display_name(code), "total_objects": 0, "active_satellites": 0},
        )
        entry["total_objects"] += 1
        obj_type = (rec.get("OBJECT_TYPE") or "").upper()
        if obj_type == "PAYLOAD" and classify_ops_status(rec.get("OPS_STATUS_CODE")) == "active":
            entry["active_satellites"] += 1

    countries = sorted(by_owner.values(), key=lambda e: -e["total_objects"])
    return {
        "source": SATCAT_SOURCE,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(onorbit),
        "metric_definitions": {
            "total_objects": "All on-orbit objects (payload + rocket body + debris) attributed to this OWNER code.",
            "active_satellites": "Payloads with an active OPS_STATUS_CODE, attributed to this OWNER code.",
            "operators": "Not available — SATCAT records ownership, not the distinct day-to-day operating entity.",
            "launches": "Not available — OWNER reflects ownership, not launch site/state.",
        },
        "countries": countries,
    }


@router.get("/orbital-snapshot/composition")
async def orbital_snapshot_composition():
    """Donut chart: active payloads / inactive payloads / rocket bodies / debris — real counts from SATCAT."""
    onorbit = await _require_satcat_onorbit()

    composition = {"active_payloads": 0, "inactive_payloads": 0, "rocket_bodies": 0, "debris": 0}
    unclassified = 0
    for rec in onorbit:
        obj_type = (rec.get("OBJECT_TYPE") or "").upper()
        if obj_type == "PAYLOAD":
            status = classify_ops_status(rec.get("OPS_STATUS_CODE"))
            if status == "active":
                composition["active_payloads"] += 1
            elif status == "inactive":
                composition["inactive_payloads"] += 1
            else:
                unclassified += 1
        elif obj_type == "ROCKET BODY":
            composition["rocket_bodies"] += 1
        elif obj_type == "DEBRIS":
            composition["debris"] += 1
        else:
            unclassified += 1

    return {
        "source": SATCAT_SOURCE,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "composition": composition,
        "unclassified_objects": unclassified,
    }


@router.get("/orbital-snapshot/altitude")
async def orbital_snapshot_altitude(
    object_type: str = Query("all", description="all | active | inactive | rocket_body | debris"),
):
    """Altitude histogram (mean of apogee/perigee), optionally filtered by object category."""
    onorbit = await _require_satcat_onorbit()

    def matches(rec: dict) -> bool:
        obj_type = (rec.get("OBJECT_TYPE") or "").upper()
        if object_type == "all":
            return True
        if object_type == "rocket_body":
            return obj_type == "ROCKET BODY"
        if object_type == "debris":
            return obj_type == "DEBRIS"
        if object_type == "active":
            return obj_type == "PAYLOAD" and classify_ops_status(rec.get("OPS_STATUS_CODE")) == "active"
        if object_type == "inactive":
            return obj_type == "PAYLOAD" and classify_ops_status(rec.get("OPS_STATUS_CODE")) == "inactive"
        return True

    labels = altitude_bin_labels()
    histogram = {label: 0 for label in labels}
    unclassified = 0
    for rec in onorbit:
        if not matches(rec):
            continue
        apogee, perigee = rec.get("APOGEE"), rec.get("PERIGEE")
        if apogee is None or perigee is None:
            unclassified += 1
            continue
        bin_label = altitude_bin((apogee + perigee) / 2)
        if bin_label:
            histogram[bin_label] += 1
        else:
            unclassified += 1

    return {
        "source": SATCAT_SOURCE,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "filter": object_type,
        "histogram": histogram,
        "objects_missing_altitude_data": unclassified,
    }


@router.get("/orbital-snapshot/regime-full")
async def orbital_snapshot_regime_full():
    """Regime breakdown across the FULL on-orbit catalog (payloads + rocket
    bodies + debris) — more complete than the active-payload-only breakdown
    in /summary's by_regime, which only sees what GROUP=active covers."""
    onorbit = await _require_satcat_onorbit()

    counts = {"LEO": 0, "MEO": 0, "GEO": 0, "GTO": 0, "HEO": 0, "OTHER": 0, "UNKNOWN": 0}
    for rec in onorbit:
        regime = classify_regime_satcat(rec.get("PERIGEE"), rec.get("APOGEE"), rec.get("PERIOD"))
        counts[regime] = counts.get(regime, 0) + 1

    return {
        "source": SATCAT_SOURCE,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "regimes": counts,
    }


# --- 3D globe: live-propagated positions -------------------------------------
# CelesTrak's free GP feed is curated by mission/type — there's a general
# `active` group (active payloads, by definition) and `stations`, plus a
# handful of NAMED debris-cloud groups from specific fragmentation events
# (each of those IS debris, by the group's own definition — no guessing
# involved). There is no general "all rocket bodies" or "all inactive
# payloads" group with propagatable elements in the free feed, so those
# aren't plotted here — same honesty rule as the KPIs in `summary()` above:
# don't imply coverage that doesn't exist. Every group fetch is independently
# wrapped so one failing (or falling back to CelesTrak's own stale cache,
# which `celestrak.py` already handles) never blanks the whole globe.
GLOBE_GROUPS = {
    "active": "PAYLOAD",
    "stations": "PAYLOAD",     # overlaps `active`, deduped below
    "cosmos-1408-debris": "DEBRIS",
    "cosmos-2251-debris": "DEBRIS",
    "iridium-33-debris": "DEBRIS",
    "fengyun-1c-debris": "DEBRIS",
}
GLOBE_DEFAULT_MAX = 4000
_globe_cache = TTLCache(maxsize=4, ttl=300)  # 5 min — SGP4 propagation is the expensive part, not the fetch


async def _fetch_group_tle_safe(group: str) -> list[dict]:
    try:
        return await fetch_group_tle(group)
    except Exception:
        return []  # this one group is unavailable right now — the rest of the globe still renders


async def _propagated_globe_objects(max_total: int) -> dict:
    if max_total in _globe_cache:
        return _globe_cache[max_total]

    fetched = await asyncio.gather(*(_fetch_group_tle_safe(g) for g in GLOBE_GROUPS))
    groups_failed = [g for g, recs in zip(GLOBE_GROUPS, fetched) if not recs]

    tle_by_norad: dict[int, dict] = {}
    type_of_norad: dict[int, str] = {}
    for group, records in zip(GLOBE_GROUPS, fetched):
        obj_type = GLOBE_GROUPS[group]
        for rec in records:
            try:
                norad_id = int(rec["line1"][2:7])
            except (ValueError, IndexError, KeyError):
                continue
            tle_by_norad[norad_id] = rec
            # payload beats debris if an id somehow appears in both (shouldn't happen, but payload is the safer default)
            if norad_id not in type_of_norad or obj_type == "PAYLOAD":
                type_of_norad[norad_id] = obj_type

    # Keep every debris object (small counts, high visual value); sample the
    # much larger `active` payload set down evenly to fit the budget.
    debris_ids = [nid for nid, t in type_of_norad.items() if t == "DEBRIS"]
    payload_ids = [nid for nid, t in type_of_norad.items() if t == "PAYLOAD"]
    budget_for_payloads = max(0, max_total - len(debris_ids))
    if len(payload_ids) > budget_for_payloads:
        step = len(payload_ids) / max(budget_for_payloads, 1)
        payload_ids = [payload_ids[int(i * step)] for i in range(budget_for_payloads)] if budget_for_payloads else []

    kept_ids = set(debris_ids) | set(payload_ids)
    truncated = len(kept_ids) < len(tle_by_norad)
    kept_records = [tle_by_norad[nid] for nid in kept_ids]

    positions = propagate_subpoints(kept_records)  # real SGP4, not estimated

    objects = []
    for norad_id, pos in positions.items():
        rec = tle_by_norad[norad_id]
        objects.append({
            "norad_id": norad_id,
            "name": rec["name"],
            "object_type": "PAYLOAD" if type_of_norad[norad_id] == "PAYLOAD" else "DEBRIS",
            "lat": pos["lat"],
            "lon": pos["lon"],
            "alt_km": pos["alt_km"],
            "regime": classify_regime(pos.get("mean_motion")),
        })

    result = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "source": "CelesTrak GP feed, SGP4-propagated (Skyfield) at request time",
        "groups_used": list(GLOBE_GROUPS),
        "groups_unavailable": groups_failed,
        "coverage_note": (
            "Live 3D positions cover active payloads, space stations, and several named debris "
            "clouds from specific tracked fragmentation events. Rocket bodies and inactive payloads "
            "aren't plotted — CelesTrak's free GP feed doesn't publish a general propagatable group "
            "for either, same limitation noted in the KPI summary above."
        ),
        "count": len(objects),
        "truncated": truncated,
        "objects": objects,
    }
    _globe_cache[max_total] = result
    return result


@router.get("/globe-objects")
async def globe_objects(max_total: int = Query(GLOBE_DEFAULT_MAX, ge=100, le=6000)):
    """Live SGP4-propagated positions for the 3D globe. Never hard-fails: a
    group that's temporarily unreachable is dropped and reported in
    `groups_unavailable` rather than failing the whole response."""
    return await _propagated_globe_objects(max_total)


@router.get("/orbit-path/{norad_id}")
async def orbit_path(norad_id: int):
    """One full orbital period of ground-track points for a single object."""
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

    return {"norad_id": norad_id, "name": tle["name"], "source": "CelesTrak GP feed, SGP4-propagated", "path": path}
