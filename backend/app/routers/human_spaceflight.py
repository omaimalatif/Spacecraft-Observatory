# Portal 07 — Human Spaceflight. Source: Open Notify (free, no key).
import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/iss-now")
async def iss_now():
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get("http://api.open-notify.org/iss-now.json")
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach Open Notify: {exc}") from exc
    return {**data, "source": "Open Notify"}


@router.get("/people-in-space")
async def people_in_space():
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get("http://api.open-notify.org/astros.json")
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach Open Notify: {exc}") from exc
    return {**data, "source": "Open Notify"}
