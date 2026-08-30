# NSO — NCGSA Spacecraft Observatory

v3: proper React frontend (components, no per-portal stock photos) + a Python
backend that does real orbital-mechanics calculations, not just data passthrough.

```
frontend/    React + Vite — components, one fixed backdrop image, glass UI
backend/     FastAPI + Skyfield/SGP4 — live CelesTrak data + orbit propagation
```

## Run it

**Backend** (Python 3.10+):
```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
Interactive API docs: http://localhost:8000/docs

**Frontend** (Node 18+), in a second terminal:
```bash
cd frontend
npm install
npm run dev
```
Open http://localhost:5173

The frontend reads `VITE_API_BASE` (see `frontend/.env.example`) — defaults to
`http://localhost:8000`, so both run out of the box with no config.

## What's actually live vs. placeholder

- **Portal 1 KPIs / regime split** — real: fetched from `/api/space-assets/summary`,
  which pulls CelesTrak's live `active` catalog and classifies each object into
  LEO/MEO/GEO/HEO from its mean motion. If the backend isn't running, the UI
  falls back to the last known public catalog sizes so the page still looks right.
- **"What's overhead" map** — real: click anywhere, pick a satellite group, and
  the backend fetches that group's live TLEs from CelesTrak, propagates every
  one with SGP4 (Skyfield), and returns only what's above your chosen elevation
  angle *right now*. This is genuine orbital mechanics, not a lookup table.
- **Debris / rocket-body / composition breakdown, altitude bars** — still the
  infographic's published figures, shown as placeholders until a similarly
  live endpoint is wired up (debris catalogs are huge; worth a dedicated,
  cached job rather than computing on every page load).
- **Portals 2–8** — designed as glass cards with real headline stats from the
  original infographic; only Portal 1 and the visibility map are wired to
  live data so far.

## Portal → data source map

| # | Portal | Backend route | Source |
|---|---|---|---|
| — | Visibility (map click) | `/api/visibility` | CelesTrak TLE + Skyfield SGP4 (real propagation) |
| 1 | Global Space Assets | `/api/space-assets/*` | CelesTrak GP catalog |
| 2 | Earth Observation | `/api/earth-observation/events` | NASA EONET v3 |
| 3 | Navigation Systems | `/api/navigation/constellations` | CelesTrak (GROUP=gnss) |
| 4 | Communication | *not yet wired* | CelesTrak (by group), FCC ICFS |
| 5 | Meteorological & Environmental | *not yet wired* | NOAA, EUMETSAT, NASA GIBS |
| 6 | Space Science & Exploration | *not yet wired* | NASA Exoplanet Archive, JPL Horizons |
| 7 | Human Spaceflight | `/api/human-spaceflight/*` | Open Notify (ISS position, people in space) |
| 8 | CubeSat & Small Satellites | *not yet wired* | CelesTrak (GROUP=cubesat), nanosats.eu |

## Adding a portal route (pattern for 4, 5, 6, 8)

1. `backend/app/routers/<portal>.py` — fetch the source above with `httpx`, shape the JSON.
2. Register it in `backend/app/main.py`: `app.include_router(<portal>.router, prefix="/api/<portal>", ...)`.
3. Add a call in `frontend/src/api.js`, then use it in that portal's component.

## Design system — glassmorphism over a single backdrop

One fixed cosmic photo behind the entire app (`src/styles/theme.css`, `.backdrop`);
everything else — header, KPI cards, dashboard, portal tiles, the map panel — is a
frosted `backdrop-filter: blur()` glass surface. No stock photography per portal;
portal cards use icon + accent color only, matching the original infographic's
information density without needing per-portal imagery.

Type: **Manrope** (headings), **Inter** (body), **JetBrains Mono** (every number).
Accent palette: cyan `#5AD1E6` (primary/live), amber `#FFB454`, magenta `#E68FBF`,
green `#8FE3C7` — each portal gets one as its accent glow.

## Logos

Real partner logos are already in place — no placeholders left:

```
frontend/public/ncgsa-logo.png          → navbar badge + footer partner row
frontend/public/partners/
  govt-of-pakistan.png
  hec.png
  ist.png
  gnss-research-lab.png
```

To swap any of these, replace the file (same name) or update the `src` in
`Header.jsx` (navbar) / the `PARTNER_LOGOS` array in `Footer.jsx` (footer row).
Each partner-row logo renders inside a white rounded "badge" card
(`.partner-badge` in `theme.css`) so mixed aspect ratios and flat white
backgrounds all sit cleanly on the dark theme — add or remove entries from
`PARTNER_LOGOS` and the row lays itself out automatically.

## Next steps

- Wire portals 4, 5, 6, 8 to their sources above.
- Cache the visibility endpoint's TLE propagation results for a few seconds so
  rapid map clicks don't each trigger a full recompute.
- Country-level attribution for Portal 1's "by country" map needs a registry
  join (UNOOSA Online Index or Space-Track) — CelesTrak's free feed doesn't
  include owner/country.
- 3D Earth / orbit visualization (Cesium or three.js) for Portal 1's globe.
