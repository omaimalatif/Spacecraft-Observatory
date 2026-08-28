# Orbital mechanics: orbit-regime classification from mean motion, and
# real satellite-visibility computation using SGP4 propagation (via Skyfield).

from datetime import datetime, timedelta, timezone
import math

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
                eccentricity = sat.model.ecco
                semi_major_axis_km = (398600.4418 / ((mean_motion_rev_per_day * 2 * 3.141592653589793 / 86400) ** 2)) ** (1 / 3) if mean_motion_rev_per_day else None
                results.append({
                    "name": rec["name"],
                    "norad_id": sat.model.satnum,
                    "elevation_deg": round(alt.degrees, 2),
                    "azimuth_deg": round(az.degrees, 2),
                    "distance_km": round(distance.km, 1),
                    "period_min": round(1440 / mean_motion_rev_per_day, 2) if mean_motion_rev_per_day else None,
                    "inclination_deg": round(math.degrees(sat.model.inclo), 2),
                    "mean_motion_rev_day": round(mean_motion_rev_per_day, 8),
                    "eccentricity": round(eccentricity, 8),
                    "mean_anomaly_deg": round(math.degrees(sat.model.mo) % 360, 4),
                    "argument_of_perigee_deg": round(math.degrees(sat.model.argpo) % 360, 4),
                    "raan_deg": round(math.degrees(sat.model.nodeo) % 360, 4),
                    "semi_major_axis_km": round(semi_major_axis_km, 1) if semi_major_axis_km is not None else None,
                    "perigee_alt_km": round(semi_major_axis_km * (1 - eccentricity) - 6378.137, 1) if semi_major_axis_km is not None else None,
                    "apogee_alt_km": round(semi_major_axis_km * (1 + eccentricity) - 6378.137, 1) if semi_major_axis_km is not None else None,
                })
        except Exception:
            continue  # skip malformed/decayed elements rather than fail the whole request

    results.sort(key=lambda r: -r["elevation_deg"])
    return results[:limit]


def compute_visible_from_omm(omm_records, lat, lon, elevation_m=0.0, min_elevation_deg=10.0, limit=100):
    """
    Same computation as compute_visible, but takes CelesTrak GP *JSON* ("OMM")
    records instead of {name, line1, line2} TLE lines — Skyfield's
    EarthSatellite.from_omm() builds the same propagator straight from those
    fields. This lets /api/visibility fall back to the JSON catalog (already
    fetched once at startup and cached ~2h) when the *separate* TLE-format
    download for the same group is rate-limited by CelesTrak, instead of
    failing outright with no usable data.
    """
    t = _ts.now()
    observer = wgs84.latlon(lat, lon, elevation_m)
    results = []

    for rec in omm_records:
        try:
            sat = EarthSatellite.from_omm(_ts, rec)
            topocentric = (sat - observer).at(t)
            alt, az, distance = topocentric.altaz()
            if alt.degrees >= min_elevation_deg:
                mean_motion_rev_per_day = sat.model.no_kozai * 1440 / (2 * 3.141592653589793)
                results.append({
                    "name": rec.get("OBJECT_NAME", sat.name),
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
            eccentricity = sat.model.ecco
            semi_major_axis_km = (398600.4418 / ((mean_motion * 2 * 3.141592653589793 / 86400) ** 2)) ** (1 / 3) if mean_motion else None
            out[sat.model.satnum] = {
                "lat": round(subpoint.latitude.degrees, 3),
                "lon": round(subpoint.longitude.degrees, 3),
                "alt_km": round(subpoint.elevation.km, 1),
                "mean_motion": mean_motion,
                "mean_motion_rev_day": round(mean_motion, 8),
                "period_min": round(1440 / mean_motion, 2) if mean_motion else None,
                "epoch": sat.epoch.utc_iso(),
                "inclination_deg": round(math.degrees(sat.model.inclo), 2),
                "eccentricity": round(eccentricity, 8),
                "mean_anomaly_deg": round(math.degrees(sat.model.mo) % 360, 4),
                "argument_of_perigee_deg": round(math.degrees(sat.model.argpo) % 360, 4),
                "raan_deg": round(math.degrees(sat.model.nodeo) % 360, 4),
                "semi_major_axis_km": round(semi_major_axis_km, 1) if semi_major_axis_km is not None else None,
                "perigee_alt_km": round(semi_major_axis_km * (1 - eccentricity) - 6378.137, 1) if semi_major_axis_km is not None else None,
                "apogee_alt_km": round(semi_major_axis_km * (1 + eccentricity) - 6378.137, 1) if semi_major_axis_km is not None else None,
            }
        except Exception:
            continue
    return out


def compute_sky_track(
    line1: str, line2: str, name: str, lat: float, lon: float,
    elevation_m: float = 0.0, window_min: int = 60, step_min: int = 3,
) -> list[dict]:
    """
    Real topocentric azimuth/elevation for one satellite across a time
    window centred on now, as actually seen from the given ground point —
    the "where does it move across my sky" track for a sky-plot's Orbits
    overlay. Points below the horizon are included (negative elevation)
    rather than dropped, so the caller can decide how to clip/fade them.
    """
    observer = wgs84.latlon(lat, lon, elevation_m)
    sat = EarthSatellite(line1, line2, name, _ts)
    now = datetime.now(timezone.utc)
    offsets = list(range(-window_min, window_min + 1, step_min))
    times = _ts.utc([now + timedelta(minutes=m) for m in offsets])

    topocentric = (sat - observer).at(times)
    alt, az, _distance = topocentric.altaz()

    return [
        {
            "minutes_from_now": offsets[i],
            "elevation_deg": round(alt.degrees[i], 2),
            "azimuth_deg": round(az.degrees[i], 2),
        }
        for i in range(len(offsets))
    ]


def compute_sky_tracks_batch(
    tle_records: list[dict], lat: float, lon: float,
    elevation_m: float = 0.0, window_min: int = 25, step_min: int = 5,
) -> dict[int, list[dict]]:
    """
    Same real SGP4 topocentric az/el track as compute_sky_track, but for
    every satellite in tle_records at once, sharing one observer + time
    array — this is what lets the sky dome draw every satellite's short
    orbit arc (not just a clicked one) without N separate requests.
    Malformed/decayed elements are skipped, not faked.
    """
    observer = wgs84.latlon(lat, lon, elevation_m)
    now = datetime.now(timezone.utc)
    offsets = list(range(-window_min, window_min + 1, step_min))
    times = _ts.utc([now + timedelta(minutes=m) for m in offsets])

    out: dict[int, list[dict]] = {}
    for rec in tle_records:
        try:
            sat = EarthSatellite(rec["line1"], rec["line2"], rec["name"], _ts)
            topocentric = (sat - observer).at(times)
            alt, az, _distance = topocentric.altaz()
            out[sat.model.satnum] = [
                {"minutes_from_now": offsets[i], "elevation_deg": round(alt.degrees[i], 2), "azimuth_deg": round(az.degrees[i], 2)}
                for i in range(len(offsets))
            ]
        except Exception:
            continue
    return out


def compute_orbit_paths_batch(tle_records: list[dict], steps: int = 72) -> dict[int, dict]:
    """
    Real SGP4-propagated orbit path for EVERY satellite in tle_records at
    once — each one sampled across its own orbital period (derived from its
    own mean motion, not a shared assumption), so the 3D globe can draw a
    genuine trajectory line for every plotted satellite, not just a single
    clicked one. Returns {norad_id: {period_min, path}}. Malformed/decayed
    elements are skipped, not faked.
    """
    now = datetime.now(timezone.utc)
    out: dict[int, dict] = {}
    for rec in tle_records:
        try:
            sat = EarthSatellite(rec["line1"], rec["line2"], rec["name"], _ts)
            mean_motion_rev_per_day = sat.model.no_kozai * 1440 / (2 * 3.141592653589793)
            if not mean_motion_rev_per_day:
                continue
            period_min = 1440 / mean_motion_rev_per_day
            times = _ts.utc([now + timedelta(minutes=(period_min * i / steps)) for i in range(steps + 1)])
            geo = sat.at(times)
            subpoints = wgs84.subpoint(geo)
            path = [
                {
                    "lat": round(subpoints.latitude.degrees[i], 3),
                    "lon": round(subpoints.longitude.degrees[i], 3),
                    "alt_km": round(subpoints.elevation.km[i], 1),
                    # Minutes from "now" for this sample — lets the frontend also
                    # render a space-fixed (inertial) version of the same path by
                    # undoing Earth's rotation over this offset, instead of only
                    # the Earth-fixed ground track above.
                    "t_min": round(period_min * i / steps, 4),
                }
                for i in range(steps + 1)
            ]
            out[sat.model.satnum] = {"period_min": round(period_min, 2), "path": path}
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
