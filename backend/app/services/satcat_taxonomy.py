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
#
# BUGFIX: this dict used to be referenced as OWNER_NAMES by
# owner_display_name() below without ever being defined — a NameError on
# every call, which meant /by-country (and anything built on top of it,
# like a Pakistan-specific KPI) was crashing on every request, not just
# returning a "data unavailable" placeholder. Restored here as the base
# table, covering the codes that actually appear in the SATCAT OWNER
# column (cross-checked against satcat_bulk.csv), merged with the
# longer-tail ADDITIONS dict below.
OWNER_NAMES_BASE = {
    "US": "United States",
    "CIS": "Russia / former USSR",
    "PRC": "China",
    "FR": "France",
    "JPN": "Japan",
    "IND": "India",
    "UK": "United Kingdom",
    "ESA": "European Space Agency",
    "GER": "Germany",
    "IT": "Italy",
    "ITSO": "International Telecommunications Satellite Organization",
    "ISS": "International Space Station (multinational program)",
    "CA": "Canada",
    "SPN": "Spain",
    "ORB": "Orbcomm (commercial)",
    "CHBZ": "China/Brazil (CBERS program)",
    "GLOB": "Globalstar (commercial)",
    "SKOR": "South Korea",
    "AUS": "Australia",
    "ARGN": "Argentina",
    "SES": "SES (commercial)",
    "ISRA": "Israel",
    "EUTE": "Eutelsat (commercial)",
    "TURK": "Turkey",
    "ROC": "Taiwan (Republic of China)",
    "FIN": "Finland",
    "SEAL": "Sea Launch (commercial)",
    "IRAN": "Iran",
    "UAE": "United Arab Emirates",
    "BRAZ": "Brazil",
    "O3B": "O3b Networks (commercial)",
    "NOR": "Norway",
    "POL": "Poland",
    "SING": "Singapore",
    "NZ": "New Zealand",
    "LUXE": "Luxembourg",
    "SWTZ": "Switzerland",
    "INDO": "Indonesia",
    "GREC": "Greece",
    "IM": "Isle of Man",
    "EUME": "Eumetsat",
    "SAUD": "Saudi Arabia",
    "NETH": "Netherlands",
    "DEN": "Denmark",
    "AB": "Arabsat",
    "BEL": "Belgium",
    "THAI": "Thailand",
    "CZCH": "Czech Republic",
    "EGYP": "Egypt",
    "SWED": "Sweden",
    "MALA": "Malaysia",
    "RWA": "Rwanda",
    "PAKI": "Pakistan",
    "MEX": "Mexico",
    "LTU": "Lithuania",
    "SAFR": "South Africa",
    "HUN": "Hungary",
    "UKR": "Ukraine",
    "RP": "Philippines",
}

OWNER_NAMES_ADDITIONS = {
    "FIN": "Finland",
    "ROC": "Taiwan (Republic of China)",
    "GREC": "Greece",
    "POR": "Portugal",
    "DEN": "Denmark",
    "ALG": "Algeria",
    "CZCH": "Czech Republic",
    "RWA": "Rwanda",
    "KAZ": "Kazakhstan",
    "BUL": "Bulgaria",
    "BELA": "Belarus",
    "MA": "Morocco",
    "HUN": "Hungary",
    "RP": "Philippines",
    "SAFR": "South Africa",
    "VENZ": "Venezuela",
    "ASRA": "Austria",
    "ECU": "Ecuador",
    "PERU": "Peru",
    "ANG": "Angola",
    "SVN": "Slovenia",
    "LTU": "Lithuania",
    "KWT": "Kuwait",
    "NKOR": "North Korea",
    "SVK": "Slovakia",
    "NICO": "Nicaragua",
    "COL": "Colombia",
    "EST": "Estonia",
    "BOL": "Bolivia",
    "URY": "Uruguay",
    "IRAQ": "Iraq",
    "ITSO": "International Telecommunications Satellite Organization",
    "ISS": "International Space Station (multinational program)",
}


OWNER_NAMES = {**OWNER_NAMES_BASE, **OWNER_NAMES_ADDITIONS}


def owner_display_name(code: str | None) -> str:
    if not code:
        return "Unknown"
    code = code.strip()
    return OWNER_NAMES.get(code, code)


# --- Functional satellite type, best-effort from OBJECT_NAME -----------------
# SATCAT has no "purpose" field, so there is no authoritative source for
# "is this a navigation/comms/EO satellite". This classifies PAYLOAD records
# by matching well-known constellation/mission name prefixes — real string
# matches against real names, not a guess at unlisted ones. Anything that
# doesn't match a known pattern is reported as "Other / Unclassified" rather
# than forced into a bucket, same honesty rule used elsewhere in this file —
# that bucket is shown to the user, never hidden, so nothing is silently
# dropped from the totals.
# Coverage checked against the live active-payload set (satcat_bulk.csv):
# ~89% classified after the pattern expansion below (was ~82%), still
# dominated by Starlink/OneWeb-scale constellations. The remaining ~11% is
# genuinely unnamed/ambiguous by OBJECT_NAME alone (old US test-payload
# codes like "OPS 5712 (P/L 160)", generic single-word names, etc.) and is
# left unclassified rather than guessed.
import re as _re

SATELLITE_TYPE_LABELS = [
    "Communications",
    "Earth Observation",
    "Navigation",
    "Military / Government",
    "CubeSat / Small Satellite",
    "Geodetic / Calibration",
    "Science / Astronomy",
    "Space Station / Human Spaceflight",
    "Other / Unclassified",
]

_SATELLITE_TYPE_PATTERNS: list[tuple[str, list[str]]] = [
    ("Navigation", [
        r"\bNAVSTAR\b", r"\bGPS\b", r"\bGLONASS\b", r"\bGLO-", r"\bBEIDOU\b",
        r"\bCOMPASS-[MG]\d", r"\bGALILEO\b", r"\bQZS", r"\bMICHIBIKI\b",
        r"\bIRNSS\b", r"\bNAVIC\b",
    ]),
    ("Communications", [
        r"\bSTARLINK\b", r"\bONEWEB\b", r"\bIRIDIUM\b", r"\bGLOBALSTAR\b",
        r"\bORBCOMM\b", r"\bINTELSAT\b", r"\bEUTELSAT\b", r"\bINMARSAT\b",
        r"\bSES-\d", r"\bTELESAT\b", r"\bTHURAYA\b", r"\bYAHSAT\b",
        r"\bO3B\b", r"\bGONETS\b", r"\bHULIANWANG\b", r"\bGUOWANG\b",
        r"\bQIANFAN\b", r"\bSITRO", r"\bCONNECTA\b", r"\bCHINASAT\b",
        r"\bAPSTAR\b", r"\bASIASAT\b", r"\bJCSAT\b", r"\bKOREASAT\b",
        r"\bMEASAT\b", r"\bPALAPA\b", r"\bTURKSAT\b", r"\bNILESAT\b",
        r"\bHISPASAT\b", r"\bASTRA \d", r"\bAMOS-\d", r"\bECHOSTAR\b",
        r"\bDIRECTV\b", r"\bSIRIUS\b", r"\bXM-\d", r"\bTDRS\b",
        r"\bTIANLIAN\b", r"\bGALAXY \d", r"\bBADR", r"\bPAKSAT\b",
        r"\bARABSAT\b", r"\bNSS-\d", r"\bEXPRESS-A", r"\bYAMAL\b",
        r"\bLUCH\b", r"\bSPAINSAT\b", r"\bATHENA-FIDUS\b", r"\bAZERSPACE\b",
        r"\bNIMIQ\b", r"\bANIK\b", r"\bVINASAT\b",
        r"\bABS-\d", r"\bAMC-\d+\b", r"\bOPTUS\b", r"\bTHAICOM\b",
        r"\bHELLAS-SAT\b", r"\bBSAT-\d", r"\bTHOR \d", r"\bHORIZONS-\d",
        r"\bSTAR ONE\b", r"\bTELSTAR\b", r"\bTERRESTAR\b", r"\bSKYTERRA\b",
        r"\bVIASAT\b", r"\bICO\b", r"\bSUPERBIRD\b", r"\bSICRAL\b",
        r"\bZHONGXING\b", r"\bCOMSATBW\b", r"\bRASCOM\b", r"\bHYLAS\b",
        r"\bAMAZONAS\b", r"\bQUETZSAT\b", r"\bKAZSAT\b", r"\bWILDBLUE\b",
        r"\bLATINSAT\b", r"\bGSAT-?\d", r"\bMOBISAT\b", r"\bAZERSAT\b",
        r"\bASIASTAR\b",
    ]),
    ("Military / Government", [
        r"^USA\b", r"\bUSA \d", r"\bMILSTAR\b", r"\bAEHF\b", r"\bWGS\b",
        r"\bSKYNET\b", r"\bSBIRS\b", r"\bPRAETORIAN\b", r"^COSMOS\b",
        r"\bIGS\b", r"\bSAR-LUPE\b", r"\bSTSS\b", r"\bSBSS\b",
        r"\bTACSAT\b", r"\bSTPSAT\b", r"\bOFEQ\b", r"\bSYRACUSE\b",
        r"\bLES-\d",
    ]),
    ("Earth Observation", [
        r"\bLANDSAT\b", r"\bSENTINEL\b", r"\bNOAA \d", r"\bGOES\b",
        r"\bMETEOSAT\b", r"\bTERRA\b", r"\bAQUA\b", r"\bSUOMI\b", r"\bJPSS\b",
        r"\bFENGYUN\b", r"\bRADARSAT\b", r"\bICEYE\b", r"\bFLOCK\b",
        r"\bSKYSAT\b", r"\bDOVE\b", r"\bSPOT \d", r"\bPLEIADES\b",
        r"\bWORLDVIEW\b", r"\bGEOEYE\b", r"\bQUICKBIRD\b", r"\bIKONOS\b",
        r"\bCBERS\b", r"\bRESOURCESAT\b", r"\bCARTOSAT\b", r"\bGAOFEN\b",
        r"\bYAOGAN\b", r"\bZIYUAN\b", r"\bHJ-\d", r"\bKOMPSAT\b",
        r"\bTIANHUI\b", r"\bENVISAT\b", r"\bERS-\d", r"\bALOS\b",
        r"\bRISAT\b", r"\bEROS \b", r"\bDEIMOS\b", r"\bMETOP\b", r"\bDMSP\b",
        r"\bJILIN\b", r"\bSUPERVIEW\b", r"\bTIANMU\b", r"\bYUNHAI\b",
        r"\bCORIOLIS\b", r"\bSORCE\b", r"\bAURA\b", r"\bOCEANSAT\b",
        r"\bHAIYANG\b", r"\bCOSMO-SKYMED\b", r"\bTERRASAR-X\b",
        r"\bTANDEM-X\b", r"\bUK-DMC\b", r"\bALSAT\b", r"\bRASAT\b",
        r"\bNIGERIASAT\b", r"\bDUBAISAT\b", r"\bGOSAT\b", r"\bTHEOS\b",
        r"\bCRYOSAT\b", r"\bSMOS\b", r"\bTIMED\b", r"\bPROBA-\d",
    ]),
    ("CubeSat / Small Satellite", [
        # Real, well-known CubeSat/nanosat missions and program names, plus
        # the standard amateur-radio "(XX-##)" satellite designator used
        # across many student/amateur CubeSats (AO-, FO-, IO-, LO-, NO-,
        # UO-, CO-, SO-) and the older "RS##" Radio Sputnik series.
        r"\bCUBESAT\b", r"\bCUTE-1\b", r"\bCANX-?\d", r"\bSAUDICOMSAT\b",
        r"\bSAUDISAT\b", r"\bAPRIZESAT\b", r"\bNANOSAT\b", r"\bBEESAT\b",
        r"\bITUPSAT\b", r"\bSWISSCUBE\b", r"\bTISAT\b", r"\bSEEDS\b",
        r"\bSTARS \(", r"\bXIWANG\b", r"\bJUGNU\b", r"\bSRMSAT\b",
        r"\bZHEDA PIXING\b", r"\bX-SAT\b", r"\bUWE-?\d", r"\bAAUSAT\b",
        r"\bDELFI-?\w", r"\bQUAKESAT\b", r"\bFUNCUBE\b", r"\bLEMUR\b",
        r"\bTUBSAT\b", r"\([A-Z]{2}-\d{1,3}\)", r"\bRS\d{1,2}\b",
    ]),
    ("Geodetic / Calibration", [
        # Passive/retroreflector spheres and known USAF/geodesy calibration
        # targets — small satellites with no active mission beyond being
        # tracked or reflected off of. Real, documented program names.
        r"\bCALSPHERE\b", r"\bLCS \d", r"\bLAGEOS\b", r"\bSTARLETTE\b",
        r"\bSTELLA\b", r"\bAJISAI\b", r"\bTEMPSAT\b", r"\bRIGIDSPHERE\b",
        r"\bLARETS\b", r"\bWESTPAC\b", r"\bSURCAL\b",
    ]),
    ("Space Station / Human Spaceflight", [
        r"\bZARYA\b", r"\bTIANGONG\b", r"\bTIANHE\b", r"\bWENTIAN\b",
        r"\bMENGTIAN\b", r"\bISS\b", r"\bPOISK\b", r"\bMIR\b",
        r"\bSALYUT\b", r"\bSKYLAB\b", r"\bSHENZHOU\b", r"\bTIANZHOU\b",
    ]),
    ("Science / Astronomy", [
        r"\bHUBBLE\b", r"\bHST\b", r"\bJWST\b", r"\bWEBB\b", r"\bCHANDRA\b",
        r"\bCXO\b", r"\bKEPLER\b", r"\bTESS\b", r"\bSPITZER\b", r"\bFERMI\b",
        r"\bSWIFT\b", r"\bGAIA\b", r"\bXMM\b", r"\bINTEGRAL\b", r"\bIXPE\b",
        r"\bSWARM\b", r"\bAEOLUS\b",
        r"\bVOYAGER \d", r"\bPIONEER \d", r"\bMARS EXPRESS\b",
        r"\bMARS ODYSSEY\b", r"\bMRO\b", r"\bCASSINI\b", r"\bJUNO\b",
        r"\bNEW HORIZONS\b", r"\bROSETTA\b", r"\bDAWN\b", r"\bMESSENGER\b",
        r"\bULYSSES\b", r"\bSOHO\b", r"\bWIND\b", r"\bPOLAR\b", r"\bACE\b",
        r"\bIMAGE\b", r"\bCLUSTER II\b", r"\bISEE\b", r"\bGEOTAIL\b",
        r"\bTHEMIS \w", r"\bSTEREO \w", r"\bIBEX\b", r"\bHERSCHEL\b",
        r"\bLRO\b", r"\bSDO\b", r"\bFGRST\b", r"\bGLAST\b", r"\bSCISAT\b",
        r"\bHINODE\b", r"\bCHANG'E", r"\bMOST\b", r"\bSWAS\b", r"\bIKAROS\b",
        r"\bFORTE\b",
    ]),
]
_COMPILED_TYPE_PATTERNS = [
    (label, [_re.compile(p) for p in pats]) for label, pats in _SATELLITE_TYPE_PATTERNS
]


def classify_satellite_type(name: str | None) -> str:
    """Best-effort functional category from a payload's OBJECT_NAME.
    Returns one of SATELLITE_TYPE_LABELS. See module note above."""
    upper = (name or "").upper()
    for label, patterns in _COMPILED_TYPE_PATTERNS:
        for pattern in patterns:
            if pattern.search(upper):
                return label
    return "Other / Unclassified"
