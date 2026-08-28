# Location resolution for the "what's overhead" map: a curated Pakistan-first
# preset list for the corner dropdown, plus free-text search (geocoding) for
# typing any place name — city, country, landmark — and getting lat/lon back.
import httpx
from fastapi import APIRouter, HTTPException, Query

from app.services.geocoding import search_place

router = APIRouter()

# Curated presets for the corner dropdown. The Institute of Space Technology
# (IST), Islamabad is PRESETS[0] and is used as the application's default
# observation point; a few major cities follow so the dropdown is useful
# without typing.
# Global presets: one representative city per populated continent/region,
# plus GNSS-relevant high-latitude and equatorial points.
GLOBAL_PRESETS = [
    {"label": "Institute of Space Technology, Islamabad", "lat": 33.52038, "lon": 73.17373, "country": "Pakistan"},
    {"label": "Islamabad, Pakistan", "lat": 33.6844, "lon": 73.0479, "country": "Pakistan"},
    {"label": "Rawalpindi, Pakistan", "lat": 33.5651, "lon": 73.0169, "country": "Pakistan"},
    {"label": "Lahore, Pakistan", "lat": 31.5204, "lon": 74.3587, "country": "Pakistan"},
    {"label": "Karachi, Pakistan", "lat": 24.8607, "lon": 67.0011, "country": "Pakistan"},
    {"label": "Peshawar, Pakistan", "lat": 34.0151, "lon": 71.5249, "country": "Pakistan"},
    {"label": "Quetta, Pakistan", "lat": 30.1798, "lon": 66.9750, "country": "Pakistan"},
    {"label": "Multan, Pakistan", "lat": 30.1575, "lon": 71.5249, "country": "Pakistan"},
    {"label": "Faisalabad, Pakistan", "lat": 31.4504, "lon": 73.1350, "country": "Pakistan"},
    {"label": "Hyderabad, Pakistan", "lat": 25.3960, "lon": 68.3578, "country": "Pakistan"},
    {"label": "Gilgit, Pakistan", "lat": 35.9208, "lon": 74.3087, "country": "Pakistan"},
    {"label": "Skardu, Pakistan", "lat": 35.2971, "lon": 75.6333, "country": "Pakistan"},
    {"label": "Washington, D.C., United States", "lat": 38.9072, "lon": -77.0369, "country": "United States"},
    {"label": "London, United Kingdom", "lat": 51.5072, "lon": -0.1276, "country": "United Kingdom"},
    {"label": "Moscow, Russia", "lat": 55.7558, "lon": 37.6173, "country": "Russia"},
    {"label": "Beijing, China", "lat": 39.9042, "lon": 116.4074, "country": "China"},
    {"label": "Tokyo, Japan", "lat": 35.6762, "lon": 139.6503, "country": "Japan"},
    {"label": "New Delhi, India", "lat": 28.6139, "lon": 77.2090, "country": "India"},
    {"label": "Nairobi, Kenya", "lat": -1.2921, "lon": 36.8219, "country": "Kenya"},
    {"label": "São Paulo, Brazil", "lat": -23.5505, "lon": -46.6333, "country": "Brazil"},
    {"label": "Sydney, Australia", "lat": -33.8688, "lon": 151.2093, "country": "Australia"},
    {"label": "Longyearbyen, Svalbard", "lat": 78.2232, "lon": 15.6267, "country": "Norway"},
    {"label": "McMurdo Station, Antarctica", "lat": -77.8419, "lon": 166.6863, "country": "Antarctica"},
]


@router.get("/presets-global")
def presets_global():
    return {"presets": GLOBAL_PRESETS, "default": GLOBAL_PRESETS[0]}


@router.get("/search-global")
async def search_global(q: str = Query(..., min_length=2)):
    try:
        results = await search_place(q, country_code=None)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach the geocoding service: {exc}") from exc
    return {"query": q, "results": results}