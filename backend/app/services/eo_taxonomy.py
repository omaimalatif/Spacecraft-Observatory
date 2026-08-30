# Best-effort classification of Earth-observation satellites by what hazard
# they're actually used to detect — CelesTrak's GROUP=resource/weather has no
# "purpose" field, same limitation as satcat_taxonomy.classify_satellite_type,
# same fix: match real, well-known mission name patterns; anything that
# doesn't match goes to "General Earth Observation" rather than a guess.
import re

HAZARD_FOCUS_LABELS = [
    "Fire Detection",
    "Storm & Weather Tracking",
    "Flood & Precipitation Monitoring",
    "General Earth Observation",
]

_HAZARD_PATTERNS: list[tuple[str, list[str]]] = [
    ("Fire Detection", [
        # MODIS (Terra/Aqua) and VIIRS (Suomi NPP, NOAA-20/21, JPSS) are the
        # instruments NASA FIRMS itself draws active-fire detections from.
        r"\bTERRA\b", r"\bAQUA\b", r"\bSUOMI\s?NPP\b", r"\bNOAA[- ]?2[01]\b",
        r"\bJPSS\b", r"\bLANDSAT\b",
    ]),
    ("Storm & Weather Tracking", [
        r"\bGOES\b", r"\bEWS-G", r"\bMETEOSAT\b", r"\bMSG-\d", r"\bHIMAWARI\b",
        r"\bFENGYUN\b", r"\bDMSP\b", r"\bINSAT\b", r"\bCOMS\b", r"\bELEKTRO\b",
        r"\bGOMS\b", r"\bMETEOR-M", r"\bNOAA \d", r"\bTIROS\b", r"\bMETOP\b",
        r"\bCYGFM", r"\bCYGNSS\b", r"\bARKTIKA\b", r"\bMTG-",
    ]),
    ("Flood & Precipitation Monitoring", [
        r"\bGPM\b", r"\bTRMM\b", r"\bSENTINEL-1\b", r"\bJASON\b", r"\bSARAL\b",
        r"\bRADARSAT\b", r"\bSMAP\b", r"\bSWOT\b", r"\bCOSMO-SKYMED\b",
        r"\bSAOCOM\b", r"\bICEYE\b",
    ]),
]
_COMPILED = [(label, [re.compile(p) for p in pats]) for label, pats in _HAZARD_PATTERNS]


def classify_hazard_focus(name: str | None) -> str:
    """Best-effort hazard-detection category from a satellite's OBJECT_NAME.
    Returns one of HAZARD_FOCUS_LABELS."""
    upper = (name or "").upper()
    for label, patterns in _COMPILED:
        for pattern in patterns:
            if pattern.search(upper):
                return label
    return "General Earth Observation"