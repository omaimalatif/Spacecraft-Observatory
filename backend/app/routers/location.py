# Location resolution for the "what's overhead" map: a curated Pakistan-first
# preset list for the corner dropdown, plus free-text search (geocoding) for
# typing any place name — city, country, landmark — and getting lat/lon back.
import httpx
from fastapi import APIRouter, HTTPException, Query

from app.services.geocoding import search_place

router = APIRouter()

# Curated presets for the corner dropdown. Pakistan first/default per the
# observatory's home country; a few major cities so the dropdown is useful
# without typing, plus a couple of global reference points.
PRESETS = [
    {"label": "Islamabad, Pakistan", "lat": 33.6844, "lon": 73.0479, "country": "Pakistan"},
    {"label": "Karachi, Pakistan", "lat": 24.8607, "lon": 67.0011, "country": "Pakistan"},
    {"label": "Lahore, Pakistan", "lat": 31.5497, "lon": 74.3436, "country": "Pakistan"},
    {"label": "Peshawar, Pakistan", "lat": 34.0151, "lon": 71.5249, "country": "Pakistan"},
    {"label": "Quetta, Pakistan", "lat": 30.1798, "lon": 66.9750, "country": "Pakistan"},
    {"label": "Gilgit, Pakistan", "lat": 35.9208, "lon": 74.3144, "country": "Pakistan"},
]


@router.get("/presets")
def presets():
    """Curated dropdown options — Pakistan-first, used as the default view."""
    return {"presets": PRESETS, "default": PRESETS[0]}


@router.get("/search")
async def search(q: str = Query(..., min_length=2, description="Place name in Pakistan, e.g. 'Multan' or 'Islamabad'")):
    """Search Pakistani places with OpenStreetMap Nominatim."""
    try:
        results = await search_place(q, country_code="pk")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach the geocoding service: {exc}") from exc
    return {"query": q, "results": results}
