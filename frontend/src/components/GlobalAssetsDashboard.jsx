import { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import CesiumGlobe from './CesiumGlobe.jsx'

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
    alt_km: o.alt_km, lat: o.lat, lon: o.lon,
    inclination_deg: null, period_min: null, eccentricity: null, epoch: null,
    hasLivePosition: true,
  }
}
function fromSearchResult(o) {
  const mm = o.MEAN_MOTION
  return {
    name: o.OBJECT_NAME, norad_id: o.NORAD_CAT_ID, cospar_id: o.OBJECT_ID, object_type: 'PAYLOAD',
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
            <i style={{ background: s.color }} />{s.label} <b>{composition ? new Intl.NumberFormat().format(composition[s.key] ?? 0) : 'Loading…'}</b>
          </li>
        ))}
      </ul>
    </>
  )
}

function CountryList({ byCountry }) {
  if (!byCountry) return <p className="loading-hint">Loading country breakdown…</p>
  const top = byCountry.countries.slice(0, 8)
  return (
    <>
      <ul className="country-list">
        {top.map((c) => (
          <li key={c.owner_code}>
            <span>{c.owner_name}</span>
            <b>{new Intl.NumberFormat().format(c.total_objects)}</b>
          </li>
        ))}
      </ul>
      <small>
        {byCountry.countries.length > 8 ? `+${byCountry.countries.length - 8} more entities · ` : ''}
        Grouped by SATCAT ownership, not launch site or day-to-day operator (kept separate — operator data unavailable).
      </small>
    </>
  )
}

function ObjectProfile({ item, onClose }) {
  if (!item) return <div className="profile-empty">Click a plotted object on the globe, or search below, to inspect it.</div>
  return (
    <div className="object-profile">
      <button className="close" onClick={onClose}>×</button>
      <span className="eyebrow">{item.hasLivePosition ? 'LIVE OBJECT PROFILE' : 'CATALOG SEARCH RESULT'}</span>
      <h3>{item.name}</h3>
      <p className="object-id">NORAD {item.norad_id} · {item.cospar_id || 'COSPAR unavailable'}</p>
      <div className="profile-grid">
        <label>Object type<b>{item.object_type === 'DEBRIS' ? 'Debris' : 'Payload'}</b></label>
        <label>Orbital regime<b>{item.regime}</b></label>
        {item.hasLivePosition ? (
          <>
            <label>Latitude<b>{num(item.lat, 2)}°</b></label>
            <label>Longitude<b>{num(item.lon, 2)}°</b></label>
          </>
        ) : (
          <>
            <label>Epoch<b>{item.epoch ? new Date(item.epoch).toLocaleDateString() : '—'}</b></label>
            <label>Eccentricity<b>{num(item.eccentricity, 5)}</b></label>
          </>
        )}
        <label>Altitude{item.hasLivePosition ? ' (current)' : ' (mean, est.)'}<b>{item.alt_km == null ? '—' : `${fmt(item.alt_km)} km`}</b></label>
        <label>Inclination<b>{item.inclination_deg != null ? `${num(item.inclination_deg, 2)}°` : '—'}</b></label>
        {item.period_min != null && <label>Period<b>{num(item.period_min, 1)} min</b></label>}
      </div>
      <p className="profile-note">Owner, operator, launch date, apogee and perigee require a registry/mission-data join and are not inferred here.</p>
    </div>
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
  const [composition, setComposition] = useState(null)
  const [byCountry, setByCountry] = useState(null)

  useEffect(() => {
    api.spaceAssetsSummary()
      .then((data) => { setSummary(data); setCatalogStatus(data?.updated_at ? 'live' : null) })
      .catch((err) => setError(err.message || 'Could not load live catalog data'))
    api.spaceAssetsComposition().then(setComposition).catch(() => setComposition(null))
    api.spaceAssetsByCountry().then(setByCountry).catch(() => setByCountry(null))
  }, [])

  const kpis = [
    ['Total catalogued objects', summary?.total_catalogued, summary?.notes?.total_catalogued ?? 'Complete compatible catalog not connected'],
    ['Active payloads', summary?.total_active, summary?.active_source ? `${summary.active_source} active inventory` : 'Active inventory'],
    ['Inactive satellites', summary?.inactive, summary?.notes?.inactive],
    ['Rocket bodies', summary?.rocket_bodies, summary?.notes?.rocket_bodies],
    ['Space debris', summary?.debris, summary?.notes?.debris],
    ['Countries / entities', summary?.countries, summary?.notes?.countries],
    ['Added in last 30 days', summary?.recently_added, 'CelesTrak GROUP=last-30-days'],
  ]

  const regimesForBars = useMemo(() => {
    const by = summary?.by_regime || {}
    return ['LEO', 'MEO', 'GEO', 'HEO', 'UNKNOWN'].map((label) => ({ label, value: by[label] ?? 0 }))
  }, [summary])

  async function submitSearch(e) {
    e.preventDefault()
    if (!query.trim()) return
    setSearching(true)
    try {
      const r = await api.searchSpaceAssets(query)
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
        <a href="#" className="wordmark"><span className="mark">◉</span><span>NCGSA</span><small>SPACECRAFT OBSERVATORY</small></a>
        <nav>
          <a href="#">← Observatory home</a>
          <a className="active">01 Global Space Assets</a>
          <a href="#snapshot">Orbital Snapshot</a>
          <a href="#sources">Data Sources</a>
        </nav>
        <span className="live-badge"><i /> LIVE DATA</span>
      </header>

      <section className="assets-intro">
        <div>
          <p className="eyebrow">PORTAL 01 / MASTER OVERVIEW</p>
          <h1>Global <em>Space Assets</em></h1>
          <p>What is currently in space, where is it, and how is the population in orbit changing?</p>
        </div>
        <div className="update-note">
          {error ? error : summary?.updated_at ? `Last refreshed ${new Date(summary.updated_at).toLocaleString()}${catalogStatus === 'cached' ? ' · cached catalog (CelesTrak refresh window)' : ''}` : 'Connecting to CelesTrak'}
          <br /><span>Source: CelesTrak GP catalog feeds, SGP4-propagated for the 3D view</span>
        </div>
      </section>

      <section className="asset-kpis">
        {kpis.map(([label, value, note]) => (
          <article key={label}>
            <span>{label}</span>
            <strong className={value == null ? 'unavailable' : ''}>{fmt(value)}</strong>
            <small>{note}</small>
          </article>
        ))}
      </section>

      <section className="command-grid">
        <article className="globe-card panel">
          <div className="panel-head">
            <div><p className="eyebrow">ORBITAL VIEW · CESIUM 3D</p><h2>Objects around Earth</h2></div>
            <span>Live SGP4-propagated positions</span>
          </div>
          <CesiumGlobe selected={selected} onSelect={(o) => setSelected(fromGlobePoint(o))} />
        </article>
        <aside className="panel profile-panel">
          <ObjectProfile item={selected} onClose={() => setSelected(null)} />
        </aside>
      </section>

      <section id="snapshot" className="snapshot">
        <div className="section-title">
          <p className="eyebrow">ORBITAL SNAPSHOT</p>
          <h2>Current active-payload distribution</h2>
          <span>Source: CelesTrak active catalog · calculated from current mean motion</span>
        </div>
        <div className="snapshot-grid">
          <article className="panel chart-card">
            <h3>Objects by orbital regime</h3>
            <BarChart data={regimesForBars} />
          </article>
          <article className="panel composition">
            <h3>Object composition</h3>
            <Donut composition={composition?.composition} />
            <small>
              {composition?.unclassified_objects > 0
                ? `${composition.unclassified_objects.toLocaleString()} objects have an unresolvable type/status and are excluded, not guessed. `
                : ''}
              Source: {composition?.source ?? 'CelesTrak SATCAT'}
            </small>
          </article>
        </div>
      </section>

      <section className="lower-grid">
        <article className="panel">
          <p className="eyebrow">SPACE ASSETS BY COUNTRY</p>
          <h2>Top owning countries / entities</h2>
          <CountryList byCountry={byCountry} />
        </article>
        <article className="panel unavailable-card">
          <p className="eyebrow">GLOBAL SPACE POPULATION GROWTH</p>
          <h2>Historical catalog growth</h2>
          <p>Data unavailable. No authoritative historical series is currently connected; this view will not display estimated or invented history.</p>
          <span>Planned source: NASA ODPO / compatible authoritative catalog history.</span>
        </article>
      </section>

      <section className="activity-grid">
        <article className="panel activity">
          <p className="eyebrow">SPACE ACTIVITY SNAPSHOT</p>
          <h2>Recent catalog activity</h2>
          <strong>{fmt(summary?.recently_added)}</strong>
          <span>objects in CelesTrak's last-30-days feed</span>
          <p>Recent re-entry and fragmentation event feeds are not connected.</p>
        </article>
        <article className="panel activity">
          <p className="eyebrow">ORBITAL ENVIRONMENT</p>
          <h2>Debris population</h2>
          <strong>{fmt(composition?.composition?.debris)}</strong>
          <span>on-orbit debris objects tracked by SATCAT</span>
          <p>Recent fragmentation-event feeds are not connected — the 3D view plots several named debris clouds as a representative sample only, not the full population above.</p>
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
                <button key={o.NORAD_CAT_ID} onClick={() => setSelected(fromSearchResult(o))}>
                  {o.OBJECT_NAME}<span>NORAD {o.NORAD_CAT_ID}</span>
                </button>
              ))}
            </div>
          )}
          <small>Search source: CelesTrak GP active payload catalog.</small>
        </article>
      </section>

      <footer className="assets-footer">
        Data attribution: <a href="https://celestrak.org/" target="_blank" rel="noreferrer">CelesTrak GP data</a> · Live data is cached server-side for up to 2 hours (CelesTrak refresh cadence). Values marked "Data unavailable" require a compatible authoritative source connection.
      </footer>
    </main>
  )
}
