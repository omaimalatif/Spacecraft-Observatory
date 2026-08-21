# Portal 02 — Earth Observation. Source: NASA EONET v3 (free, no key).
import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/events")
async def events():
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get("https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=50")
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach NASA EONET: {exc}") from exc

    events_list = data.get("events", [])
    return {"count": len(events_list), "events": events_list, "source": "NASA EONET v3"}
