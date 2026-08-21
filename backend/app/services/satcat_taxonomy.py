# Classification helpers for CelesTrak SATCAT records — turning raw fields
# (OBJECT_TYPE, OPS_STATUS_CODE, OWNER, APOGEE/PERIGEE/PERIOD) into what the
# Global Space Assets portal needs. Thresholds are standard orbital-regime
# definitions, not fitted values.

# OPS_STATUS_CODE legend, as published by CelesTrak (celestrak.org/satcat/status.php):
#   +  Operational        P  Partially Operational   B  Backup/Standby
#   S  Spare               X  Extended Mission        D  Decayed
#   -  Nonoperational      ?  Unknown
_ACTIVE_CODES = {"+", "P", "B", "S", "X"}
_INACTIVE_CODES = {"-", "D"}


def classify_ops_status(code: str | None) -> str:
    """-> 'active' | 'inactive' | 'unknown'. Only meaningful for OBJECT_TYPE=PAYLOAD."""
    if not code:
        return "unknown"
    code = code.strip()
    if code in _ACTIVE_CODES:
        return "active"
    if code in _INACTIVE_CODES:
        return "inactive"
    return "unknown"


def classify_regime(perigee_km: float | None, apogee_km: float | None, period_min: float | None) -> str:
    """
    LEO/MEO/GEO/GTO/HEO from CelesTrak's own computed apogee/perigee/period —
    validated against ISS (LEO), GPS (MEO), Intelsat (GEO), a genuine GTO
    transfer orbit, and Molniya (HEO, apogee well past GEO — the case that
    made GTO's naive "apogee >= 30000" threshold wrong; tightened below).
    """
    if perigee_km is None or apogee_km is None:
        return "UNKNOWN"

    mean_alt = (perigee_km + apogee_km) / 2
    spread = apogee_km - perigee_km

    if period_min and 1350 <= period_min <= 1500 and spread < 3000:
        return "GEO"
    if 33000 <= apogee_km <= 38000 and perigee_km < 8000:
        return "GTO"
    if apogee_km > 38000 and spread > 8000:
        return "HEO"
    if mean_alt < 2000:
        return "LEO"
    if 2000 <= mean_alt < 35786:
        return "MEO"
    if mean_alt >= 35786:
        return "HEO" if spread >= 3000 else "GEO"
    return "OTHER"


_ALTITUDE_BINS = [
    (0, 500, "0-500 km"),
    (500, 1000, "500-1,000 km"),
    (1000, 2000, "1,000-2,000 km"),
    (2000, 5000, "2,000-5,000 km"),
    (5000, 20000, "5,000-20,000 km"),
    (20000, 35000, "20,000-35,000 km"),
    (35000, 40000, "35,000-40,000 km"),
]
_ALTITUDE_OVERFLOW_LABEL = "40,000+ km"


def altitude_bin(mean_alt_km: float | None) -> str | None:
    if mean_alt_km is None:
        return None
    for low, high, label in _ALTITUDE_BINS:
        if low <= mean_alt_km < high:
            return label
    return _ALTITUDE_OVERFLOW_LABEL


def altitude_bin_labels() -> list[str]:
    return [label for _, _, label in _ALTITUDE_BINS] + [_ALTITUDE_OVERFLOW_LABEL]


# OWNER is a short registry code, not free text. Maps the common ones for
# display; anything unlisted shows its raw code rather than a guess.
OWNER_NAMES = {
    "US": "United States", "CIS": "Russia / CIS", "PRC": "China", "IND": "India",
    "JPN": "Japan", "FR": "France", "UK": "United Kingdom", "ESA": "European Space Agency",
    "CA": "Canada", "GER": "Germany", "ITA": "Italy", "SES": "SES (Luxembourg)",
    "IM": "Intelsat", "AB": "ABS", "SPN": "Spain", "BRAZ": "Brazil", "RASC": "Russia",
    "UAE": "United Arab Emirates", "SKOR": "South Korea", "ISRA": "Israel",
    "AUS": "Australia", "NETH": "Netherlands", "LUXE": "Luxembourg", "ARGN": "Argentina",
    "IRAN": "Iran", "PRK": "North Korea", "TURK": "Turkey", "INDO": "Indonesia",
    "THAI": "Thailand", "MEX": "Mexico", "EGYP": "Egypt", "SAUD": "Saudi Arabia",
    "NOR": "Norway", "SWED": "Sweden", "SWTZ": "Switzerland", "BEL": "Belgium",
    "SGPR": "Singapore", "MALA": "Malaysia", "VTNM": "Vietnam", "NZ": "New Zealand",
    "PAKI": "Pakistan", "NIGR": "Nigeria", "STCT": "Global (multinational operator)",
    "O3B": "O3b Networks", "ORB": "Orbcomm", "GLOB": "Globalstar",
}


def owner_display_name(code: str | None) -> str:
    if not code:
        return "Unknown"
    code = code.strip()
    return OWNER_NAMES.get(code, code)
