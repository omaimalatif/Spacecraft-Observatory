"""
FastAPI application. This is the ONLY layer allowed to talk to
CelesTrak / Space-Track (see ingestion.py). The React frontend calls
this API and never the upstream providers directly.

Run with:
    uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from ingestion import SUPPORTED_GROUPS, CelesTrakClient, SpaceTrackClient
from models import SpaceObject

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

app = FastAPI(
    title="Global Space Assets API",
    description=(
        "Normalized orbital object catalog, sourced primarily from "
        "CelesTrak GP data with Space-Track as a secondary verification "
        "source. See /docs for endpoints."
    ),
    version="0.1.0",
)

# In production, restrict this to the actual frontend origin(s).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

celestrak = CelesTrakClient()
space_track = SpaceTrackClient()


@app.on_event("shutdown")
def _shutdown():
    celestrak.close()
    space_track.close()


@app.get("/api/groups")
def list_groups():
    """Which CelesTrak GP groups this API currently supports."""
    return {"groups": [{"id": k, "label": v} for k, v in SUPPORTED_GROUPS.items()]}


@app.get("/api/objects", response_model=None)
def get_objects(
    group: str = Query("STATIONS", description="CelesTrak GP group id"),
    force_refresh: bool = Query(False),
    include_raw: bool = Query(False, description="Include raw source record (debug/provenance only)"),
    search: Optional[str] = Query(None, description="Case-insensitive substring match on object name"),
    regime: Optional[str] = Query(None, description="Filter by orbit regime: LEO/MEO/GEO/HEO"),
):
    """The core catalog endpoint used by the dashboard."""
    try:
        entry = celestrak.get_group(group, force_refresh=force_refresh)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Upstream fetch failed: {exc}") from exc

    objects = entry.objects
    if search:
        needle = search.lower()
        objects = [o for o in objects if o.object_name and needle in o.object_name.lower()]
    if regime:
        objects = [o for o in objects if o.derived.orbit_regime == regime.upper()]

    payload = []
    for o in objects:
        d = o.dict(exclude={"raw_source_record"} if not include_raw else set())
        payload.append(d)

    return {
        "group": group,
        "count": len(payload),
        "dropped_on_ingest": entry.dropped,
        "fetched_at": entry.fetched_at,
        "objects": payload,
    }


@app.get("/api/stats")
def get_stats(group: str = Query("STATIONS")):
    """Aggregate KPIs for the dashboard -- computed server-side from
    the same normalized objects used everywhere else, never invented."""
    try:
        entry = celestrak.get_group(group)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Upstream fetch failed: {exc}") from exc

    objects: list[SpaceObject] = entry.objects
    regime_counts = Counter(o.derived.orbit_regime for o in objects)
    freshness_counts = Counter(o.orbital_provenance.data_status for o in objects)

    inclinations = [o.elements.inclination for o in objects if o.elements.inclination is not None]
    altitudes = [
        (o.derived.apogee_altitude_km + o.derived.perigee_altitude_km) / 2
        for o in objects
        if o.derived.apogee_altitude_km is not None and o.derived.perigee_altitude_km is not None
    ]

    return {
        "group": group,
        "total_objects": len(objects),
        "dropped_on_ingest": entry.dropped,
        "fetched_at": entry.fetched_at,
        "regime_counts": regime_counts,
        "freshness_counts": freshness_counts,
        "inclination_avg_deg": round(sum(inclinations) / len(inclinations), 2) if inclinations else None,
        "altitude_avg_km": round(sum(altitudes) / len(altitudes), 2) if altitudes else None,
    }


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "space_track_configured": space_track.configured,
    }
