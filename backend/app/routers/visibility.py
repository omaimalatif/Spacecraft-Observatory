# Location-based visibility: click a point on the map (or search a place) and
# get every satellite in the chosen catalog group currently above the horizon
# there, computed with real SGP4 propagation — not a lookup table.
import httpx
from fastapi import APIRouter, HTTPException, Query
from app.services.celestrak import fetch_group_tle, fetch_group_json
from app.services.orbital import compute_visible, compute_visible_from_omm
from app.services.local_time import resolve_local_time

router = APIRouter()

# Curated CelesTrak groups sensible to offer in the frontend dropdown.
# (Full list: https://celestrak.org/NORAD/elements/)
GROUP_OPTIONS = [
    {"id": "stations", "label": "Space Stations"},
    {"id": "active", "label": "Active Satellites"},
    {"id": "gnss", "label": "GNSS / Navigation"},
    {"id": "starlink", "label": "Starlink"},
    {"id": "oneweb", "label": "OneWeb"},
    {"id": "weather", "label": "Weather"},
    {"id": "geo", "label": "Geostationary"},
    {"id": "science", "label": "Science"},
    {"id": "cubesat", "label": "CubeSats"},
]

# Large groups get capped before propagation so a request stays responsive.
MAX_CHECK = 3000


@router.get("/groups")
def list_groups():
    return {"groups": GROUP_OPTIONS}


@router.get("")
async def visible_satellites(
    lat: float = Query(..., ge=-90, le=90, description="Clicked latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Clicked longitude"),
    elevation_m: float = Query(0, description="Ground elevation above sea level, metres"),
    min_elevation_deg: float = Query(10, ge=0, le=90, description="Minimum elevation angle to count as 'visible'"),
    group: str = Query("stations", description="CelesTrak group to search, see /groups"),
    limit: int = Query(100, le=500),
):
    try:
        tle_records = await fetch_group_tle(group)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach CelesTrak: {exc}") from exc
    except RuntimeError:
        # CelesTrak rate-limits each (GROUP, FORMAT) pair independently, so a
        # TLE-format download can be blocked even though the JSON format for
        # the same group was already warmed at startup and is sitting in
        # cache. Fall back to that instead of failing the request outright —
        # same real SGP4 propagation, just built from the OMM/JSON fields.
        try:
            omm_records = await fetch_group_json(group)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Could not reach CelesTrak: {exc}") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        checked = omm_records[:MAX_CHECK]
        # Count every satellite above the elevation threshold, not just the
        # slice we return for the panel's list — visible_count must be the
        # true total, independent of `limit`.
        all_visible = compute_visible_from_omm(
            checked, lat, lon, elevation_m=elevation_m, min_elevation_deg=min_elevation_deg, limit=len(checked)
        )
        return {
            "location": {"lat": lat, "lon": lon, "elevation_m": elevation_m},
            "group": group,
            "catalog_size": len(omm_records),
            "checked_count": len(checked),
            "visible_count": len(all_visible),
            "min_elevation_deg": min_elevation_deg,
            "satellites": all_visible[:limit],
            "time": resolve_local_time(lat, lon),
            "source": "CelesTrak GP JSON (OMM) + Skyfield SGP4 propagation, computed at request time",
        }

    checked = tle_records[:MAX_CHECK]

    # Same principle as above: compute the full visible set for an accurate
    # count, then hand back only `limit` of them for the satellite list.
    all_visible = compute_visible(
        checked, lat, lon, elevation_m=elevation_m, min_elevation_deg=min_elevation_deg, limit=len(checked)
    )

    return {
        "location": {"lat": lat, "lon": lon, "elevation_m": elevation_m},
        "group": group,
        "catalog_size": len(tle_records),
        "checked_count": len(checked),
        "visible_count": len(all_visible),
        "min_elevation_deg": min_elevation_deg,
        "satellites": all_visible[:limit],
        "time": resolve_local_time(lat, lon),
        "source": "CelesTrak GP TLE + Skyfield SGP4 propagation, computed at request time",
    }