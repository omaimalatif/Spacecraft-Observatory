# Global Space Assets

Orbital catalog dashboard. CelesTrak (primary) → FastAPI backend
(ingest/normalize/cache) → React frontend. Space-Track is wired in
as a secondary/verification source. See the spec this was built
against for the full data-source architecture reasoning.

```
project/
├── backend/     FastAPI service — the ONLY thing that talks to
│                CelesTrak / Space-Track. See backend/README.md.
└── frontend/    Vite + React dashboard — calls only the backend API.
```

## Quick start

**1. Backend**

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Verify: `curl http://localhost:8000/api/health`

**2. Frontend**

```bash
cd frontend
cp .env.example .env      # points at http://localhost:8000 by default
npm install
npm run dev
```

Open the printed local URL (typically http://localhost:5173).

## What happens if you skip step 1

The frontend will show a labeled amber banner ("Backend unreachable")
and fall back to a small local demo dataset — every row in that case
is tagged `UNAVAILABLE`, never presented as real. That's intentional:
the spec this was built from is explicit that mock data must be
clearly isolated and labeled, never presented as live.

## Verification notes

The core math (Keplerian orbit-regime derivation, Kepler's-equation
position solver used by the 3D globe) was tested against known
reference orbits (ISS, GPS, GEO, a Molniya-type HEO orbit) — see the
commit history / conversation this was built in for the test scripts.
One real bug was caught and fixed this way: orbit regime was
originally classified by *mean* altitude, which misclassified
high-eccentricity HEO orbits (low perigee, very high apogee) as MEO;
it's now classified by apogee altitude instead.

This container had no network egress, so the FastAPI server itself
(which needs `fastapi`/`pydantic`/`httpx` installed) and a live
CelesTrak fetch were not exercised end-to-end here — do that in your
own environment before treating this as production-verified.
