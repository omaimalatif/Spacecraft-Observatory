import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import PortalMenu from './PortalMenu.jsx'

const CesiumGlobe = lazy(() => import('./CesiumGlobe.jsx'))

const fmt = (n) => n == null ? 'Data unavailable' : new Intl.NumberFormat().format(n)
const num = (n, digits = 0) => Number.isFinite(Number(n)) ? Number(n).toFixed(digits) : '—'
const regimeFromMeanMotion = (meanMotion) => {
  const period = 1440 / Number(meanMotion)
  if (!Number.isFinite(period)) return 'Other'
  if (period < 128) return 'LEO'
  if (period > 1000 && period < 1300) return 'GEO'
  if (period <= 1000) return 'MEO'
  return 'HEO'
}
const altitudeFromMeanMotion = (meanMotion) => {
  const n = Number(meanMotion)
  if (!n) return null
  const radius = Math.cbrt(398600.4418 / ((n * 2 * Math.PI / 86400) ** 2))
  return Math.round(radius - 6378.137)
}

// The dashboard deals with two different object shapes: live-propagated
// points clicked on the Cesium globe (norad_id/lat/lon/alt_km/regime, from
// /globe-objects), and OMM search results (NORAD_CAT_ID/MEAN_MOTION/etc,
// from /search). Both get normalized to one shape before display so
// ObjectProfile doesn't need to know which source it came from.
function fromGlobePoint(o) {
  return {
    name: o.name, norad_id: o.norad_id, object_type: o.object_type, regime: o.regime,
    alt_km: o.alt_km, lat: o.lat, lon: o.lon, ops_status: o.ops_status, satellite_type: o.satellite_type,
    inclination_deg: o.inclination_deg, period_min: o.period_min, eccentricity: o.eccentricity, epoch: o.epoch,
    mean_motion_rev_day: o.mean_motion_rev_day, mean_anomaly_deg: o.mean_anomaly_deg,
    argument_of_perigee_deg: o.argument_of_perigee_deg, raan_deg: o.raan_deg,
    semi_major_axis_km: o.semi_major_axis_km, perigee_alt_km: o.perigee_alt_km, apogee_alt_km: o.apogee_alt_km,
    hasLivePosition: true,
  }
}
function fromSearchResult(o) {
  const mm = o.MEAN_MOTION
  return {
    name: o.OBJECT_NAME, norad_id: o.NORAD_CAT_ID, cospar_id: o.OBJECT_ID, object_type: 'PAYLOAD',
    ops_status: o.OPS_STATUS ?? 'active', satellite_type: o.SATELLITE_TYPE,
    regime: regimeFromMeanMotion(mm), alt_km: altitudeFromMeanMotion(mm), lat: null, lon: null,
    inclination_deg: o.INCLINATION, period_min: mm ? 1440 / mm : null, eccentricity: o.ECCENTRICITY, epoch: o.EPOCH,
    hasLivePosition: false,
  }
}

function BarChart({ data }) {
  const max = Math.max(...data.map((x) => x.value), 1)
  return (
    <div className="bar-chart">
      {data.map((x) => (
        <div className="bar-row" key={x.label}>
          <span>{x.label}</span>
          <div className="bar-track"><i style={{ width: `${(x.value / max) * 100}%` }} /></div>
          <b>{fmt(x.value)}</b>
        </div>
      ))}
    </div>
  )
}

function Donut({ composition }) {
  const slices = [
    { key: 'active_payloads', label: 'Active payloads', color: '#62d6ff' },
    { key: 'inactive_payloads', label: 'Inactive payloads', color: '#7d8795' },
    { key: 'rocket_bodies', label: 'Rocket bodies', color: '#bf91ff' },
    { key: 'debris', label: 'Debris', color: '#ffae5e' },
  ]
  const total = slices.reduce((sum, s) => sum + (composition?.[s.key] ?? 0), 0)
  let cursor = 0
  const stops = slices.map((s) => {
    const value = composition?.[s.key] ?? 0
    const pct = total ? (value / total) * 100 : 0
    const stop = `${s.color} ${cursor}% ${cursor + pct}%`
    cursor += pct
    return stop
  })
  const gradient = total ? `conic-gradient(${stops.join(', ')})` : 'conic-gradient(#1c2a33 0% 100%)'

  return (
    <>
      <div className="donut" style={{ background: gradient }}>
        <div><b>{total ? new Intl.NumberFormat().format(total) : '—'}</b><span>on-orbit objects</span></div>
      </div>
      <ul>
        {slices.map((s) => (
          <li key={s.key}>
            <i style={{ background: s.color }} />
            <span>{s.label}</span>
            <b>{composition ? new Intl.NumberFormat().format(composition[s.key] ?? 0) : 'Loading…'}</b>
          </li>
        ))}
      </ul>
    </>
  )
}

function CountryList({ byCountry, highlightCode }) {
  if (!byCountry) return <p className="loading-hint">Loading country breakdown…</p>
  const top = byCountry.countries.slice(0, 8)
  const highlighted = highlightCode && !top.some((c) => c.owner_code === highlightCode)
    ? byCountry.countries.find((c) => c.owner_code === highlightCode)
    : null
  return (
    <>
      <p className="panel-lead">Tracked objects owned or registered to each country and organization, including satellites, rocket bodies, and debris.</p>
      <ul className="country-list">
        {top.map((c) => (
          <li key={c.owner_code} className={c.owner_code === highlightCode ? 'is-highlighted' : ''}>
            <span title={c.owner_name}>{c.owner_name}</span>
            <b>{new Intl.NumberFormat().format(c.total_objects)}</b>
          </li>
        ))}
        {highlighted && (
          <li className="is-highlighted is-detached">
            <span title={highlighted.owner_name}>{highlighted.owner_name} <small>(#{byCountry.countries.indexOf(highlighted) + 1})</small></span>
            <b>{new Intl.NumberFormat().format(highlighted.total_objects)}</b>
          </li>
        )}
      </ul>
      <small>
        {byCountry.countries.length > 8 ? `+${byCountry.countries.length - 8} more entities · ` : ''}
        Grouped by SATCAT ownership, not launch site or day-to-day operator (kept separate — operator data unavailable).
      </small>
    </>
  )
}

const CATEGORY_COLORS = ['#62d6ff', '#e68fbf', '#ffb454', '#8fe3c7', '#bf91ff', '#ffae5e', '#c9a227', '#4ec7ed']

// Small line-icons per category, drawn on the fly (no icon library in this
// project) so each card is identifiable at a glance instead of a 2-letter
// monogram. Falls back to a generic satellite glyph for unknown labels.
const CATEGORY_ICON_PATHS = {
  'Communications': 'M4 15a12 12 0 0 1 12-12M4 15a8 8 0 0 1 8-8M4 15a4 4 0 0 1 4-4M4 15l7 7M15 20l5-5-2.5-2.5L15 15z',
  'Earth Observation': 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c2.5 2.4 4 5.6 4 9s-1.5 6.6-4 9c-2.5-2.4-4-5.6-4-9s1.5-6.6 4-9z',
  'Navigation': 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM15 9l-3.5 3.5L8 16l3.5-3.5z',
  'Military / Government': 'M12 3l7 3v6c0 4.5-3 7.7-7 9-4-1.3-7-4.5-7-9V6z',
  'CubeSat / Small Satellite': 'M4 8l8-4 8 4-8 4-8-4zM4 8v8l8 4 8-4V8M12 12v8',
  'Geodetic / Calibration': 'M12 3v3M12 18v3M3 12h3M18 12h3M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8z',
  'Science / Astronomy': 'M5 21l6.5-13L18 3l-3 6.5L5 21zM14 4l1.5 1.5M17.5 7.5 19 9',
  'Space Station / Human Spaceflight': 'M2 9h4v6H2zM18 9h4v6h-4zM6 12h12M9 8h6v8H9z',
}
const CATEGORY_ICON_FALLBACK = 'M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 11v10M8 16l-3 3M16 16l3 3'

function CategoryIcon({ label }) {
  const d = CATEGORY_ICON_PATHS[label] || CATEGORY_ICON_FALLBACK
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  )
}

function CategoryCards({ types }) {
  if (!types) return <p className="loading-hint">Loading satellite categories…</p>
  const named = types.types.filter((t) => t.label !== 'Other / Unclassified' && t.total > 0)
  const unmatched = types.types.find((t) => t.label === 'Other / Unclassified')
  return (
    <div className="category-cards">
      {named.map((t, i) => (
        <article className="category-card" key={t.label} style={{ '--cc': CATEGORY_COLORS[i % CATEGORY_COLORS.length] }}>
          <span className="category-badge"><CategoryIcon label={t.label} /></span>
          <div className="category-body">
            <h4>{t.label}</h4>
            <strong>{fmt(t.total)}</strong>
            <small>{fmt(t.active)} currently active</small>
          </div>
        </article>
      ))}
      {unmatched && unmatched.total > 0 && (
        <article className="category-card is-unmatched">
          <span className="category-badge">?</span>
          <div className="category-body">
            <h4>Not yet identified by name</h4>
            <strong>{fmt(unmatched.total)}</strong>
            <small>{fmt(unmatched.active)} active · name doesn't match a known satellite or constellation yet</small>
          </div>
        </article>
      )}
    </div>
  )
}

function PakistanPanel({ pakistan }) {
  if (pakistan === undefined) return <p className="loading-hint">Loading Pakistan-flagged objects…</p>
  if (!pakistan || pakistan.total_objects === 0) {
    return <p className="loading-hint">No objects currently attributed to Pakistan (OWNER=PAKI) in SATCAT.</p>
  }
  return (
    <>
      <p className="panel-lead">All tracked objects registered to Pakistan, with current status and orbital regime.</p>
      <ul className="owner-object-list">
        {pakistan.objects.map((o) => (
          <li key={o.norad_id}>
            <span className="owner-obj-name" title={o.name}>{o.name}</span>
            <span className={`owner-obj-status ${o.ops_status || 'na'}`}>
              {o.ops_status === 'active' ? 'Active' : o.ops_status === 'inactive' ? 'Inactive' : o.object_type === 'DEB' ? 'Debris' : o.object_type === 'R/B' ? 'Rocket body' : 'Unknown'}
            </span>
            <span className="owner-obj-regime">{o.regime}</span>
          </li>
        ))}
      </ul>
      <small>
        {pakistan.active_satellites} active of {pakistan.total_objects} SATCAT-attributed objects (OWNER=PAKI).
      </small>
    </>
  )
}

export default function GlobalAssetsDashboard() {
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState(null)
  const [catalogStatus, setCatalogStatus] = useState(null)
  const [selected, setSelected] = useState(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)
  const [composition, setComposition] = useState(null)
  const [byCountry, setByCountry] = useState(null)
  const [types, setTypes] = useState(null)
  const [regimeFull, setRegimeFull] = useState(null)
  const [pakistan, setPakistan] = useState(undefined)

  useEffect(() => {
    api.spaceAssetsSummary()
      .then((data) => { setSummary(data); setCatalogStatus(data?.updated_at ? 'live' : null) })
      .catch((err) => setError(err.message || 'Could not load live catalog data'))
    api.spaceAssetsComposition().then(setComposition).catch(() => setComposition(null))
    api.spaceAssetsByCountry().then(setByCountry).catch(() => setByCountry(null))
    api.spaceAssetsTypes().then(setTypes).catch(() => setTypes(null))
    api.spaceAssetsRegimeFull('payload').then(setRegimeFull).catch(() => setRegimeFull(null))
    api.spaceAssetsByCountryDetail('PAKI').then(setPakistan).catch(() => setPakistan(null))
  }, [])

  const pakistanCount = byCountry?.countries?.find((c) => c.owner_code === 'PAKI')

  const KPI_COLORS = ['#62d6ff', '#8fe3c7', '#71e8b4', '#a4b0ba', '#ffae5e', '#bf91ff', '#4ec7ed']

  const kpis = [
    ['Total catalogued objects', summary?.total_catalogued, summary?.notes?.total_catalogued ?? 'Payloads + rocket bodies + debris'],
    ['Number of satellites', summary?.total_payloads, summary?.notes?.total_payloads ?? 'All on-orbit payloads (active + inactive)'],
    ['Active satellites', summary?.total_active, summary?.active_source ? `${summary.active_source} active inventory` : 'Active inventory'],
    ['Inactive satellites', summary?.inactive, summary?.notes?.inactive],
    ['Space debris', summary?.debris, summary?.notes?.debris],
    ['Countries / entities', summary?.countries, summary?.notes?.countries],
    ['Pakistan satellites', pakistanCount?.total_objects, pakistanCount ? `${pakistanCount.active_satellites} currently active · SATCAT OWNER=PAKI` : 'SATCAT OWNER=PAKI'],
  ]

  const regimesForBars = useMemo(() => {
    const by = regimeFull?.regimes || summary?.by_regime || {}
    const labels = regimeFull ? ['LEO', 'MEO', 'GEO', 'GTO', 'HEO', 'UNKNOWN'] : ['LEO', 'MEO', 'GEO', 'HEO', 'UNKNOWN']
    return labels.map((label) => ({ label, value: by[label] ?? 0 }))
  }, [summary, regimeFull])

  async function submitSearch(e) {
    e.preventDefault()
    const normalizedQuery = query.trim().toLowerCase()
    if (!normalizedQuery) return
    setHasSearched(true)
    setSearching(true)
    try {
      const r = await api.searchSpaceAssets(normalizedQuery)
      setResults(r.objects || [])
      if (r.objects?.[0]) setSelected(fromSearchResult(r.objects[0]))
    } catch {
      setResults([])
    } finally {
      setSearching(false)
    }
  }

  return (
    <main className="assets-page">
      <header className="assets-header">
        <a href="#" className="wordmark"><img className="assets-brand-logo" src="/ncgsa-logo.png" alt="NCGSA logo" /><span>NCGSA</span><small>SPACECRAFT OBSERVATORY</small></a>
        <nav>
          <a href="#">← Observatory home</a>
          <PortalMenu />
          <a className="active">01 Global Space Assets</a>
        </nav>
        <span className="live-badge" role="status"><i /> LIVE</span>
      </header>

      <section className="assets-intro">
        <div>
          <p className="eyebrow">PORTAL 01</p>
          <h1>Global <em>Space Assets</em></h1>
          <p>Monitor the objects orbiting Earth, including active and inactive satellites, rocket bodies, and space debris. Compare them by owner, type, status, and orbital regime using live catalog data.</p>
        </div>
        <div className="update-note">
          {error ? error : summary?.updated_at ? `Last refreshed ${new Date(summary.updated_at).toLocaleString()}${catalogStatus === 'cached' ? ' · cached catalog (CelesTrak refresh window)' : ''}` : 'Connecting to CelesTrak'}
          <br /><span>Live SGP4-propagated positions</span>
        </div>
      </section>

      <section className="asset-kpis">
        {kpis.map(([label, value], i) => {
          const tooltips = {
            'Total catalogued objects': 'All tracked objects: satellites + rocket bodies + debris',
            'Number of satellites': 'Active + inactive payloads only (excludes debris & rocket bodies)',
            'Active satellites': 'Currently operational payloads only (from live inventory)',
            'Inactive satellites': 'Non-operational payloads still tracked in orbit',
            'Space debris': 'Fragmentation debris and spent rocket stages',
            'Countries / entities': 'Unique owners/operators of tracked objects',
            'Pakistan satellites': 'Objects registered to Pakistan in SATCAT (OWNER=PAKI)',
          }
          return (
            <article
              key={label}
              style={{ '--kpi-color': KPI_COLORS[i % KPI_COLORS.length] }}
              title={tooltips[label]}
              className="kpi-with-tooltip"
            >
            <span>{label}</span>
            <strong className={value == null ? 'unavailable' : ''}>{fmt(value)}</strong>
          </article>
          )
        })}
      </section>

      <section className="command-grid">
        <article className="globe-card panel">
          <div className="panel-head">
            <div><p className="eyebrow">ORBITAL VIEW · CESIUM 3D</p><h2>Objects around Earth</h2></div>
            <span title="Live SGP4-propagated positions of active payloads only (excludes debris & rocket bodies)">Live SGP4-propagated positions</span>
          </div>
          <Suspense fallback={<div className="globe-loading" role="status">Loading orbital view…</div>}>
            <CesiumGlobe selected={selected} onSelect={(o) => setSelected(fromGlobePoint(o))} onClose={() => setSelected(null)} />
          </Suspense>
        </article>
        <aside className="assets-chart-stack">
          <article className="panel chart-card" title="Payloads only by orbital regime (excludes rocket bodies & debris)">
            <h3>Satellites by orbital regime</h3>
            <BarChart data={regimesForBars} />
          </article>
          <article className="panel composition" title="Breakdown of all objects by type: active payloads, inactive payloads, rocket bodies, debris">
            <h3>Object composition</h3>
            <Donut composition={composition?.composition} />
          </article>
        </aside>
      </section>

      <section className="category-section">
        <div className="section-title">
          <p className="eyebrow">SATELLITES BY CATEGORY</p>
          <h2>Breakdown by mission type</h2>
          <span>Includes all active and inactive payloads, sorted by primary mission class</span>
        </div>
        <CategoryCards types={types} />
      </section>

      <section className="lower-grid">
        <article className="panel">
          <p className="eyebrow">SPACE ASSETS BY COUNTRY</p>
          <h2>Top orbital owners</h2>
          <CountryList byCountry={byCountry} highlightCode="PAKI" />
        </article>
        <article className="panel">
          <p className="eyebrow">PAKISTAN'S SPACE OBJECTS</p>
          <h2>Currently in orbit</h2>
          <PakistanPanel pakistan={pakistan} />
        </article>
      </section>

      <section className="activity-grid">
        <article className="panel activity">
          <p className="eyebrow">SPACE ACTIVITY SNAPSHOT</p>
          <h2>Recent catalog activity</h2>
          <strong>{fmt(summary?.recently_added)}</strong>
          <span>objects added in the last 30 days</span>
          <p>Recent re-entry and fragmentation event feeds are not connected.</p>
        </article>
        <article id="sources" className="panel search-card">
          <p className="eyebrow">GLOBAL SPACE OBJECT SEARCH</p>
          <h2>Locate a catalogued payload</h2>
          <form onSubmit={submitSearch}>
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search satellite, NORAD ID, COSPAR ID…" />
            <button>{searching ? 'Searching…' : 'Search'}</button>
          </form>
          {results.length > 0 && (
            <div className="search-results">
              {results.slice(0, 4).map((o) => (
                <button type="button" key={o.NORAD_CAT_ID} onClick={() => setSelected(fromSearchResult(o))}>
                  {o.OBJECT_NAME}<span>NORAD {o.NORAD_CAT_ID}</span>
                </button>
              ))}
            </div>
          )}
          {!searching && hasSearched && results.length === 0 && (
            <p className="search-empty">No matching active payload found. Try a satellite name, NORAD ID, or COSPAR ID.</p>
          )}
        </article>
      </section>

      <footer className="assets-footer">
        Data attribution: <a href="https://celestrak.org/" target="_blank" rel="noreferrer">CelesTrak GP data</a> · Live data is cached server-side for up to 2 hours (CelesTrak refresh cadence). Values marked "Data unavailable" require a compatible authoritative source connection.
      </footer>
    </main>
  )
}
