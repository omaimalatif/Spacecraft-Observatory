# Orbital mechanics: orbit-regime classification from mean motion, and
# real satellite-visibility computation using SGP4 propagation (via Skyfield).

from datetime import datetime, timedelta, timezone

from skyfield.api import EarthSatellite, load, wgs84

_ts = load.timescale()


def classify_regime(mean_motion) -> str:
    """Classify an orbit regime from mean motion (revolutions/day)."""
    if not mean_motion:
        return "UNKNOWN"
    period_min = 1440 / mean_motion
    if period_min < 128:
        return "LEO"
    if 1000 < period_min < 1300:
        return "GEO"
    if 128 <= period_min <= 1000:
        return "MEO"
    return "HEO"


def compute_visible(tle_records, lat, lon, elevation_m=0.0, min_elevation_deg=10.0, limit=100):
    """
    For each {name, line1, line2} TLE record, propagate to *now* with SGP4
    and compute topocentric altitude/azimuth from the given ground location.
    Returns satellites currently above `min_elevation_deg`, sorted highest-first.
    """
    t = _ts.now()
    observer = wgs84.latlon(lat, lon, elevation_m)
    results = []

    for rec in tle_records:
        try:
            sat = EarthSatellite(rec["line1"], rec["line2"], rec["name"], _ts)
            topocentric = (sat - observer).at(t)
            alt, az, distance = topocentric.altaz()
            if alt.degrees >= min_elevation_deg:
                mean_motion_rev_per_day = sat.model.no_kozai * 1440 / (2 * 3.141592653589793)
                results.append({
                    "name": rec["name"],
                    "norad_id": sat.model.satnum,
                    "elevation_deg": round(alt.degrees, 2),
                    "azimuth_deg": round(az.degrees, 2),
                    "distance_km": round(distance.km, 1),
                    "period_min": round(1440 / mean_motion_rev_per_day, 2) if mean_motion_rev_per_day else None,
                })
        except Exception:
            continue  # skip malformed/decayed elements rather than fail the whole request

    results.sort(key=lambda r: -r["elevation_deg"])
    return results[:limit]


def propagate_subpoints(tle_records: list[dict], at=None) -> dict[int, dict]:
    """
    Propagate every {name, line1, line2} record to a single instant (default:
    now) via real SGP4 and return {norad_id: {lat, lon, alt_km, mean_motion}}
    — the actual ground-track subpoint used to place each object on the 3D
    globe, plus mean motion for regime classification. Malformed/decayed
    elements are skipped, not faked.
    """
    t = at or _ts.now()
    out: dict[int, dict] = {}
    for rec in tle_records:
        try:
            sat = EarthSatellite(rec["line1"], rec["line2"], rec["name"], _ts)
            geo = sat.at(t)
            subpoint = wgs84.subpoint(geo)
            mean_motion = sat.model.no_kozai * 1440 / (2 * 3.141592653589793)
            out[sat.model.satnum] = {
                "lat": round(subpoint.latitude.degrees, 3),
                "lon": round(subpoint.longitude.degrees, 3),
                "alt_km": round(subpoint.elevation.km, 1),
                "mean_motion": mean_motion,
            }
        except Exception:
            continue
    return out


def compute_orbit_path(line1: str, line2: str, name: str, steps: int = 90) -> list[dict]:
    """
    Propagate a single satellite forward across one full orbital period
    (derived from its own mean motion, not assumed), sampled at `steps`
    evenly-spaced points — the ground track drawn when a user asks to see
    an object's orbit.
    """
    sat = EarthSatellite(line1, line2, name, _ts)
    mean_motion_rev_per_day = sat.model.no_kozai * 1440 / (2 * 3.141592653589793)
    if not mean_motion_rev_per_day:
        return []
    period_min = 1440 / mean_motion_rev_per_day

    now = datetime.now(timezone.utc)
    times = _ts.utc([now + timedelta(minutes=(period_min * i / steps)) for i in range(steps + 1)])

    geo = sat.at(times)
    subpoints = wgs84.subpoint(geo)
    return [
        {
            "lat": round(subpoints.latitude.degrees[i], 3),
            "lon": round(subpoints.longitude.degrees[i], 3),
            "alt_km": round(subpoints.elevation.km[i], 1),
        }
        for i in range(steps + 1)
    ]
