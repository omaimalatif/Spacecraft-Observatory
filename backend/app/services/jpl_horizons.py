# NASA/JPL Horizons — the authoritative source for solar-system ephemerides.
# Free, no API key. https://ssd-api.jpl.nasa.gov/doc/horizons.html
#
# Every position this module returns is CALCULATED FROM EPHEMERIS, not a live
# telemetry feed — Horizons computes state vectors from tracked orbital
# solutions. Callers must label results accordingly (see the "source" field
# each function returns) rather than present them as real-time telemetry.
#
# Major-body IDs (verified against Horizons' own major-body index, not
# memorized — see https://ssd.jpl.nasa.gov/api/horizons.api?COMMAND='A*'):
#   10=Sun, 199=Mercury, 299=Venus, 399=Earth, 499=Mars,
#   599=Jupiter, 699=Saturn, 799=Uranus, 899=Neptune
#
# Spacecraft IDs are NOT memorized/guessed — they're resolved at request time
# via Horizons' own Lookup API (resolve_spkid below), which is the officially
# documented way to correlate a mission name to its correct SPK-ID. This
# avoids presenting a wrong ID's data as if it were the requested spacecraft.

from datetime import datetime, timedelta, timezone

import httpx
from cachetools import TTLCache

HORIZONS_API = "https://ssd.jpl.nasa.gov/api/horizons.api"
LOOKUP_API = "https://ssd.jpl.nasa.gov/api/horizons_lookup.api"

MAJOR_BODIES = {
    "sun": "10", "mercury": "199", "venus": "299", "earth": "399",
    "mars": "499", "jupiter": "599", "saturn": "699", "uranus": "799", "neptune": "899",
}

# State vectors change continuously but slowly relative to a page session —
# cache for 30 min to stay responsive without hammering JPL.
_vector_cache = TTLCache(maxsize=64, ttl=1800)
# Name -> SPK-ID resolution never changes for a given mission — cache long.
_spkid_cache = TTLCache(maxsize=64, ttl=7 * 24 * 3600)


class HorizonsError(Exception):
    pass


async def resolve_spkid(name: str) -> str | None:
    """Look up a spacecraft/body's Horizons SPK-ID by name — the documented,
    correct way to get an ID rather than guessing one from memory."""
    if name in _spkid_cache:
        return _spkid_cache[name]

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(LOOKUP_API, params={"sstr": name, "format": "json"})
        r.raise_for_status()
        data = r.json()

    results = data.get("result") or []
    # Prefer an exact spacecraft match if one exists among the returned candidates.
    spacecraft = next((x for x in results if x.get("type") == "spacecraft"), None)
    chosen = spacecraft or (results[0] if results else None)
    spkid = chosen["spkid"] if chosen else None
    _spkid_cache[name] = spkid
    return spkid


def _parse_vector_block(text: str) -> dict:
    """Extract the first data row between $$SOE/$$EOE markers from a
    CSV_FORMAT=YES VECTORS response."""
    if "$$SOE" not in text or "$$EOE" not in text:
        raise HorizonsError(f"Horizons did not return a vector table: {text[:300]}")

    block = text.split("$$SOE", 1)[1].split("$$EOE", 1)[0].strip()
    first_line = block.splitlines()[0]
    fields = [f.strip() for f in first_line.split(",")]
    # CSV_FORMAT=YES, VEC_TABLE=1 -> JDTDB, Calendar Date, X, Y, Z, VX, VY, VZ, (trailing comma)
    if len(fields) < 8:
        raise HorizonsError(f"Unexpected Horizons vector row format: {first_line}")

    return {
        "jd_tdb": float(fields[0]),
        "calendar_date": fields[1],
        "x_au": float(fields[2]), "y_au": float(fields[3]), "z_au": float(fields[4]),
        "vx_au_day": float(fields[5]), "vy_au_day": float(fields[6]), "vz_au_day": float(fields[7]),
    }


async def get_state_vector(command_id: str) -> dict:
    """
    Real heliocentric state vector for `command_id` (a Horizons COMMAND
    value) at the current moment, computed by JPL Horizons — an
    EPHEMERIS-DERIVED position, not live telemetry.
    """
    if command_id in _vector_cache:
        return _vector_cache[command_id]

    now = datetime.now(timezone.utc)
    start = now.strftime("%Y-%m-%d %H:%M")
    stop = (now + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")

    params = {
        "format": "text",
        "COMMAND": f"'{command_id}'",
        "OBJ_DATA": "NO",
        "MAKE_EPHEM": "YES",
        "EPHEM_TYPE": "VECTORS",
        "CENTER": "'@0'",  # Solar System Barycenter
        "START_TIME": f"'{start}'",
        "STOP_TIME": f"'{stop}'",
        "STEP_SIZE": "'1d'",
        "VEC_TABLE": "1",
        "REF_SYSTEM": "'J2000'",
        "REFERENCE_PLANE": "'ECLIPTIC'",
        "OUT_UNITS": "'AU-D'",
        "CSV_FORMAT": "YES",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(HORIZONS_API, params=params)
        r.raise_for_status()
        text = r.text

    vector = _parse_vector_block(text)
    vector["command"] = command_id
    vector["computed_at"] = now.isoformat()
    vector["source"] = "NASA/JPL Horizons (EPHEMERIS-DERIVED, Solar System Barycenter frame)"

    _vector_cache[command_id] = vector
    return vector
