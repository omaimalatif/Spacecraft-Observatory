# Global Space Assets — backend

Real ingestion service for the dashboard: CelesTrak (primary) →
normalize → FastAPI → frontend. Space-Track is wired in as a
secondary/verification source, credentials server-side only.

```
CelesTrak GP JSON
      │
      ▼
ingestion.py (CelesTrakClient) ── cached, rate-limited
      │
      ▼
normalize.py ── validates fields, derives orbit regime/altitude/period
      │          (Keplerian two-body approx from mean motion + eccentricity)
      ▼
models.py (SpaceObject) ── normalized shape, provenance preserved
      │
      ▼
main.py (FastAPI) ── /api/objects, /api/stats, /api/groups
      │
      ▼
React frontend (fetches ONLY this API, never CelesTrak/Space-Track directly)
```

## Run it

```bash
pip install -r requirements.txt
export SPACE_TRACK_USERNAME=...   # optional, only needed for verification jobs
export SPACE_TRACK_PASSWORD=...
uvicorn main:app --reload --port 8000
```

Then:
- `GET /api/groups` — supported CelesTrak GP groups
- `GET /api/objects?group=STATIONS` — normalized catalog objects
- `GET /api/stats?group=STATIONS` — aggregate KPIs for the dashboard
- `GET /api/health`
- `GET /docs` — interactive Swagger UI

## Notes / what's intentionally NOT done yet

- **Space-Track enrichment job**: `SpaceTrackClient.query_gp` is a
  minimal reference client. There's no scheduled job calling it yet —
  add one (cron/Celery/etc.) that periodically cross-checks a sample
  of objects and writes discrepancies somewhere visible, rather than
  querying it per-request.
- **Persistent storage**: the cache in `ingestion.py` is in-memory,
  single-process. Fine for a demo/reference build; swap for
  Postgres/Redis before running multiple instances.
- **Enrichment sources** (ESA DISCOSweb, NASA open data, Wikidata) —
  deliberately not integrated yet per the spec ("don't make these
  mandatory for the first dashboard"). `country` / `operator` fields
  exist on `SpaceObject` and are `None` until that's wired up.
- **Freshness, not "LIVE"**: `/api/stats` and `/api/objects` report
  `data_status` (CURRENT/RECENT/STALE/UNAVAILABLE) based on the GP
  element set's own `EPOCH`, not on request time — GP data is a
  snapshot, so the dashboard should never claim it's live-streaming.
