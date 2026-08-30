# ORBITAL backend — FastAPI + Skyfield/SGP4
# Aggregates open, free space-data APIs and does real orbital-mechanics
# calculations (visibility from a clicked location) server-side.
#
# Run:  uvicorn app.main:app --reload --port 8000
# Docs: http://localhost:8000/docs   (FastAPI auto-generated, interactive)

import asyncio
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # picks up backend/.env (e.g. FIRMS_MAP_KEY) before any router reads os.environ

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import space_assets, visibility, human_spaceflight, navigation, earth_observation, location, space_science, communication, sci_satellites, meteorological
from app.services.celestrak import close_client, warmup_catalog
from app.services.satcat import close_client as close_satcat_client, warmup as warmup_satcat

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm CelesTrak/SATCAT caches once at startup so the first page load does
    # not block on a cold fetch (and so we never double-hit rate-limited groups).
    asyncio.create_task(warmup_catalog())
    asyncio.create_task(warmup_satcat())
    yield
    await close_client()
    await close_satcat_client()


app = FastAPI(
    title="ORBITAL API",
    description="Backend for the NCGSA Spacecraft Observatory — live space-asset data and orbital calculations.",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your frontend origin before production
    allow_methods=["*"],
    allow_headers=["*"],
)


# Safety net: an exception that escapes a route handler otherwise reaches the
# browser as a bare connection failure with no CORS header, which looks like
# a "blocked request" in dev tools rather than the real backend error. Every
# router already wraps its own external calls, but this catches anything
# unforeseen so the frontend always gets a readable JSON error instead.
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    return JSONResponse(status_code=500, content={"detail": f"Unexpected backend error: {exc}"})


@app.get("/api/health")
def health():
    return {"ok": True, "service": "orbital-backend-py"}


# Portal 01 — Global Space Assets (CelesTrak GP catalog)
app.include_router(space_assets.router, prefix="/api/space-assets", tags=["01 · Space Assets"])

# Location visibility — click a point on the map, see what's overhead right now
app.include_router(visibility.router, prefix="/api/visibility", tags=["Visibility (map click)"])

# Location search — Pakistan-first presets + free-text geocoding for the corner search box
app.include_router(location.router, prefix="/api/location", tags=["Location search"])

# Portal 02 — Earth Observation (NASA EONET)
app.include_router(earth_observation.router, prefix="/api/earth-observation", tags=["02 · Earth Observation"])

# Portal 03 — Navigation Systems (CelesTrak GNSS group)
app.include_router(navigation.router, prefix="/api/navigation", tags=["03 · Navigation"])

# Portal 07 — Human Spaceflight (Open Notify)
app.include_router(human_spaceflight.router, prefix="/api/human-spaceflight", tags=["07 · Human Spaceflight"])

# Portal 06 — Space Science & Exploration (JPL Horizons + NASA NeoWs)
app.include_router(space_science.router, prefix="/api/space-science", tags=["06 · Space Science"])

# Portal 06 add-on — Space Science satellite tracking (CelesTrak GROUP=science)
app.include_router(sci_satellites.router, prefix="/api/space-science-sat", tags=["06 · Space Science (satellites)"])

# Portal 04 — Communication Satellite Systems (CelesTrak comm groups)
app.include_router(communication.router, prefix="/api/communication", tags=["04 · Communication"])

# Portal 05 — Meteorological & Environmental Satellites (CelesTrak GROUP=weather)
app.include_router(meteorological.router, prefix="/api/meteorological", tags=["05 · Meteorological"])

# Portal 08 follows the exact same pattern — see backend/README section
# "Adding a portal route" for the CelesTrak group / source to wire up next.
