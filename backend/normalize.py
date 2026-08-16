"""
Normalization layer: turns raw CelesTrak GP JSON records into
SpaceObject models, deriving orbit regime / altitude / period from
the raw mean motion + eccentricity via a two-body (Keplerian)
approximation.

This is deliberately defensive -- CelesTrak does not guarantee every
field is present on every record, catalog number formats vary, and
malformed records should be skipped (with a reason logged) rather
than crashing ingestion.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Iterable

from dateutil import parser as dateparser

from models import (
    DataFreshness,
    DerivedOrbit,
    OrbitalElements,
    OrbitRegime,
    Provenance,
    SpaceObject,
    utcnow,
)

logger = logging.getLogger("ingestion.normalize")

EARTH_RADIUS_KM = 6378.137
EARTH_MU_KM3_S2 = 398600.4418  # standard gravitational parameter

# Regime thresholds (altitude of a circularized orbit, km above surface)
LEO_MAX_ALT_KM = 2000
MEO_MAX_ALT_KM = 35586   # just below GEO
GEO_BAND_KM = (35586, 35986)  # GEO is a narrow band around ~35,786 km


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _parse_epoch(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        dt = dateparser.parse(str(raw))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError, OverflowError):
        logger.warning("Unparseable EPOCH value: %r", raw)
        return None


def classify_freshness(epoch: datetime | None) -> DataFreshness:
    """Freshness is about how old the orbital element set is, not
    whether we're streaming updates -- GP data is a snapshot, never
    'LIVE'."""
    if epoch is None:
        return DataFreshness.UNAVAILABLE
    age_hours = (utcnow() - epoch).total_seconds() / 3600
    if age_hours < 0:
        return DataFreshness.UNAVAILABLE  # clock skew / bad data
    if age_hours <= 48:
        return DataFreshness.CURRENT
    if age_hours <= 24 * 14:
        return DataFreshness.RECENT
    return DataFreshness.STALE


def derive_orbit(elements: OrbitalElements) -> DerivedOrbit:
    """Two-body Keplerian approximation from mean motion + eccentricity.
    NOT a full SGP4 propagation -- sufficient for altitude/regime
    classification and dashboard charts, not for precise position."""

    if elements.mean_motion is None or elements.mean_motion <= 0:
        return DerivedOrbit()

    try:
        n_rad_s = elements.mean_motion * 2 * math.pi / 86400.0  # rev/day -> rad/s
        semi_major_axis_km = (EARTH_MU_KM3_S2 / (n_rad_s ** 2)) ** (1.0 / 3.0)
        ecc = elements.eccentricity if elements.eccentricity is not None else 0.0

        apogee_km = semi_major_axis_km * (1 + ecc) - EARTH_RADIUS_KM
        perigee_km = semi_major_axis_km * (1 - ecc) - EARTH_RADIUS_KM
        period_minutes = 1440.0 / elements.mean_motion

        # Classify by APOGEE, not mean altitude. A Molniya-type HEO orbit
        # has a low perigee that drags the *mean* of (apogee+perigee)/2
        # down into MEO/LEO range even though the orbit is clearly HEO
        # by its high point -- apogee is what actually characterizes it.
        regime = OrbitRegime.UNKNOWN
        if apogee_km <= LEO_MAX_ALT_KM:
            regime = OrbitRegime.LEO
        elif GEO_BAND_KM[0] <= apogee_km <= GEO_BAND_KM[1] and ecc < 0.05:
            regime = OrbitRegime.GEO
        elif apogee_km <= MEO_MAX_ALT_KM:
            regime = OrbitRegime.MEO
        else:
            regime = OrbitRegime.HEO

        return DerivedOrbit(
            semi_major_axis_km=round(semi_major_axis_km, 2),
            apogee_altitude_km=round(apogee_km, 2),
            perigee_altitude_km=round(perigee_km, 2),
            period_minutes=round(period_minutes, 2),
            orbit_regime=regime,
        )
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        logger.warning("Failed to derive orbit: %s", exc)
        return DerivedOrbit()


def normalize_gp_record(
    raw: dict[str, Any],
    provider: str = "CelesTrak",
    retrieved_at: datetime | None = None,
) -> SpaceObject | None:
    """Normalize one raw CelesTrak GP JSON record. Returns None (and
    logs) for records too malformed to be usable at all -- e.g. no
    identifying catalog number -- rather than raising, so one bad
    record can't take down a whole ingestion batch."""

    norad_id = _safe_str(raw.get("NORAD_CAT_ID"))
    if norad_id is None:
        logger.warning("Dropping record with no NORAD_CAT_ID: %r", raw)
        return None

    epoch = _parse_epoch(raw.get("EPOCH"))

    elements = OrbitalElements(
        mean_motion=_safe_float(raw.get("MEAN_MOTION")),
        eccentricity=_safe_float(raw.get("ECCENTRICITY")),
        inclination=_safe_float(raw.get("INCLINATION")),
        ra_of_asc_node=_safe_float(raw.get("RA_OF_ASC_NODE")),
        arg_of_pericenter=_safe_float(raw.get("ARG_OF_PERICENTER")),
        mean_anomaly=_safe_float(raw.get("MEAN_ANOMALY")),
        ephemeris_type=int(raw["EPHEMERIS_TYPE"]) if raw.get("EPHEMERIS_TYPE") not in (None, "") else None,
        classification_type=_safe_str(raw.get("CLASSIFICATION_TYPE")),
        element_set_no=int(raw["ELEMENT_SET_NO"]) if raw.get("ELEMENT_SET_NO") not in (None, "") else None,
        rev_at_epoch=_safe_float(raw.get("REV_AT_EPOCH")),
        bstar=_safe_float(raw.get("BSTAR")),
        mean_motion_dot=_safe_float(raw.get("MEAN_MOTION_DOT")),
        mean_motion_ddot=_safe_float(raw.get("MEAN_MOTION_DDOT")),
    )

    return SpaceObject(
        object_name=_safe_str(raw.get("OBJECT_NAME")),
        object_id=_safe_str(raw.get("OBJECT_ID")),
        norad_cat_id=norad_id,
        elements=elements,
        derived=derive_orbit(elements),
        orbital_provenance=Provenance(
            provider=provider,
            source_id=norad_id,
            retrieved_at=retrieved_at or utcnow(),
            epoch=epoch,
            data_status=classify_freshness(epoch),
        ),
        raw_source_record=raw,
    )


def normalize_batch(
    raw_records: Iterable[dict[str, Any]],
    provider: str = "CelesTrak",
) -> tuple[list[SpaceObject], int]:
    """Returns (normalized_objects, dropped_count)."""
    retrieved_at = utcnow()
    out: list[SpaceObject] = []
    dropped = 0
    for raw in raw_records:
        try:
            obj = normalize_gp_record(raw, provider=provider, retrieved_at=retrieved_at)
        except Exception:  # noqa: BLE001 - defensive: never let one bad
            logger.exception("Unexpected error normalizing record: %r", raw)
            obj = None
        if obj is None:
            dropped += 1
        else:
            out.append(obj)
    return out, dropped
