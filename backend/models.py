"""
Data models for the Global Space Assets platform.

These are the normalized, application-facing shapes. Raw provider
records (CelesTrak GP JSON, Space-Track REST responses) are validated
and mapped into these models by the ingestion layer -- the frontend
and the rest of the app never see raw provider payloads.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class DataFreshness(str, Enum):
    CURRENT = "CURRENT"
    RECENT = "RECENT"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


class OrbitRegime(str, Enum):
    LEO = "LEO"
    MEO = "MEO"
    GEO = "GEO"
    HEO = "HEO"  # includes highly elliptical / super-GEO / unclassified-high
    UNKNOWN = "UNKNOWN"


class Provenance(BaseModel):
    provider: str
    source_id: Optional[str] = None
    retrieved_at: datetime
    epoch: Optional[datetime] = None
    data_status: DataFreshness = DataFreshness.UNAVAILABLE


class OrbitalElements(BaseModel):
    """Fields as returned by CelesTrak GP JSON. All optional -- a
    record missing a field should still normalize, just with that
    field left null rather than the whole record being dropped."""

    mean_motion: Optional[float] = None            # revs/day
    eccentricity: Optional[float] = None
    inclination: Optional[float] = None             # degrees
    ra_of_asc_node: Optional[float] = None           # degrees (RAAN)
    arg_of_pericenter: Optional[float] = None        # degrees
    mean_anomaly: Optional[float] = None             # degrees
    ephemeris_type: Optional[int] = None
    classification_type: Optional[str] = None
    element_set_no: Optional[int] = None
    rev_at_epoch: Optional[float] = None
    bstar: Optional[float] = None
    mean_motion_dot: Optional[float] = None
    mean_motion_ddot: Optional[float] = None


class DerivedOrbit(BaseModel):
    """Computed from raw orbital elements. Never trust these blindly --
    they come from a two-body approximation (Kepler's third law), not
    a full SGP4 propagation, and are meant for dashboard-level
    classification/visualization, not operational conjunction analysis."""

    semi_major_axis_km: Optional[float] = None
    apogee_altitude_km: Optional[float] = None
    perigee_altitude_km: Optional[float] = None
    period_minutes: Optional[float] = None
    orbit_regime: OrbitRegime = OrbitRegime.UNKNOWN


class SpaceObject(BaseModel):
    """The normalized, application-facing representation of one
    catalog object (satellite, station, debris, rocket body, ...)."""

    object_name: Optional[str] = None
    object_id: Optional[str] = None                 # international designator
    norad_cat_id: Optional[str] = None               # kept as string: some
                                                      # provider formats are
                                                      # not purely numeric
    country: Optional[str] = None                    # from enrichment, not GP
    operator: Optional[str] = None                   # from enrichment, not GP

    elements: OrbitalElements = Field(default_factory=OrbitalElements)
    derived: DerivedOrbit = Field(default_factory=DerivedOrbit)

    orbital_provenance: Provenance
    metadata_provenance: Optional[Provenance] = None

    raw_source_record: Optional[dict[str, Any]] = None  # preserved for
                                                          # debugging/provenance,
                                                          # not sent to the
                                                          # frontend by default

    class Config:
        use_enum_values = True


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
