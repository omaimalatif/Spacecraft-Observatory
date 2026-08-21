# Portal 03 — Navigation Systems. Source: CelesTrak GNSS group (free, no key).
import httpx
from fastapi import APIRouter, HTTPException
from app.services.celestrak import fetch_group_json

router = APIRouter()


@router.get("/constellations")
async def constellations():
    try:
        data = await fetch_group_json("gnss")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach CelesTrak: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    by_constellation: dict[str, int] = {}
    for sat in data:
        name = (sat.get("OBJECT_NAME") or "UNKNOWN").split(" ")[0]
        by_constellation[name] = by_constellation.get(name, 0) + 1

    return {
        "total": len(data),
        "by_constellation": by_constellation,
        "source": "CelesTrak GP catalog (GROUP=gnss)",
    }
