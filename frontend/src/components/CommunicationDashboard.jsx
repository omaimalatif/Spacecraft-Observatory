
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import CommGlobe, { CATEGORY_COLOR, CATEGORY_ORDER } from './CommGlobe.jsx'
import CommSkyPlot from './CommSkyPlot.jsx'
import LocationSearch from './LocationSearch.jsx'
import CommLocationPicker from './CommLocationPicker.jsx'
import PortalMenu from './PortalMenu.jsx'

const fmt = (n) => n == null ? 'Data unavailable' : new Intl.NumberFormat().format(n)
const num = (n, digits = 0) => Number.isFinite(Number(n)) ? Number(n).toFixed(digits) : '—'

const CORE_ORDER = [...CATEGORY_ORDER, 'Other']

function fromSkyPlotPoint(s) {
  return {
    name: s.name, norad_id: s.norad_id, category: s.category, regime: null,
    alt_km: null, lat: null, lon: null,
    inclination_deg: s.inclination_deg ?? null, period_min: s.period_min, eccentricity: s.eccentricity ?? null, epoch: s.epoch ?? null,
    mean_motion_rev_day: s.mean_motion_rev_day ?? null, mean_anomaly_deg: s.mean_anomaly_deg ?? null,
    argument_of_perigee_deg: s.argument_of_perigee_deg ?? null, raan_deg: s.raan_deg ?? null,
    semi_major_axis_km: s.semi_major_axis_km ?? null, perigee_alt_km: s.perigee_alt_km ?? null, apogee_alt_km: s.apogee_alt_km ?? null,
    hasLivePosition: false,
  }
}

function fromGlobePoint(o) {
  return {
    name: o.name, norad_id: o.norad_id, category: o.category, regime: o.regime,
    alt_km: o.alt_km, lat: o.lat, lon: o.lon,
    inclination_deg: o.inclination_deg ?? null, period_min: null, eccentricity: o.eccentricity ?? null, epoch: o.epoch ?? null,
    mean_motion_rev_day: o.mean_motion_rev_day ?? null, mean_anomaly_deg: o.mean_anomaly_deg ?? null,
    argument_of_perigee_deg: o.argument_of_perigee_deg ?? null, raan_deg: o.raan_deg ?? null,
    semi_major_axis_km: o.semi_major_axis_km ?? null, perigee_alt_km: o.perigee_alt_km ?? null, apogee_alt_km: o.apogee_alt_km ?? null,
    hasLivePosition: true,
  }
}
function fromSatelliteResult(s) {
  return {
    name: s.name, norad_id: s.norad_id, cospar_id: s.cospar_id, category: s.category,
    regime: s.regime, alt_km: null, lat: null, lon: null,
    inclination_deg: s.inclination_deg, period_min: s.period_min, eccentricity: s.eccentricity, epoch: s.epoch,
    mean_motion_rev_day: s.mean_motion_rev_day, mean_anomaly_deg: s.mean_anomaly_deg,
    argument_of_perigee_deg: s.argument_of_perigee_deg, raan_deg: s.raan_deg,
    semi_major_axis_km: s.semi_major_axis_km, perigee_alt_km: s.perigee_alt_km, apogee_alt_km: s.apogee_alt_km,
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
          <div className="bar-track"><i style={{ width: `${(x.value / max) * 100}%`, background: x.color ? `linear-gradient(90deg, ${x.color}66, ${x.color})` : undefined }} /></div>
          <b>{fmt(x.value)}</b>
        </div>
      ))}
    </div>
  )
}

function ObjectProfile({ item, onClose }) {
  if (!item) return <div className="profile-empty">Click a plotted satellite on the globe, or search below, to inspect it.</div>
  return (
    <div className="object-profile">
      <button className="close" onClick={onClose}>×</button>
      <span className="eyebrow">{item.hasLivePosition ? 'LIVE SATELLITE PROFILE' : 'CATALOG SEARCH RESULT'}</span>
      <h3>{item.name}</h3>
      <p className="object-id">NORAD {item.norad_id} · {item.cospar_id || 'COSPAR unavailable'}</p>
      <div className="profile-grid">
        <label>Category<b style={{ color: CATEGORY_COLOR[item.category] }}>{item.category}</b></label>
        <label>Orbital regime<b>{item.regime}</b></label>
        {item.hasLivePosition && <label>Latitude<b>{num(item.lat, 2)}°</b></label>}
        {item.hasLivePosition && <label>Longitude<b>{num(item.lon, 2)}°</b></label>}
        <label>Epoch<b>{item.epoch ? new Date(item.epoch).toLocaleDateString() : '—'}</b></label>
        <label>Eccentricity<b>{num(item.eccentricity, 5)}</b></label>
        <label>Altitude{item.hasLivePosition ? ' (current)' : ' (mean, est.)'}<b>{item.alt_km == null ? '—' : `${fmt(item.alt_km)} km`}</b></label>
        <label>Inclination<b>{item.inclination_deg != null ? `${num(item.inclination_deg, 2)}°` : '—'}</b></label>
        {item.period_min != null && <label>Period<b>{num(item.period_min, 1)} min</b></label>}
        <label>Mean motion<b>{item.mean_motion_rev_day != null ? `${num(item.mean_motion_rev_day, 6)} rev/day` : '—'}</b></label>
        <label>Mean anomaly<b>{item.mean_anomaly_deg != null ? `${num(item.mean_anomaly_deg, 2)}°` : '—'}</b></label>
        <label>Argument of perigee<b>{item.argument_of_perigee_deg != null ? `${num(item.argument_of_perigee_deg, 2)}°` : '—'}</b></label>
        <label>RAAN<b>{item.raan_deg != null ? `${num(item.raan_deg, 2)}°` : '—'}</b></label>
        <label>Semi-major axis<b>{item.semi_major_axis_km != null ? `${fmt(item.semi_major_axis_km)} km` : '—'}</b></label>
        <label>Perigee altitude<b>{item.perigee_alt_km != null ? `${fmt(item.perigee_alt_km)} km` : '—'}</b></label>
        <label>Apogee altitude<b>{item.apogee_alt_km != null ? `${fmt(item.apogee_alt_km)} km` : '—'}</b></label>
      </div>
    </div>
  )
}

function AvailabilityPanel({ onSelect, presets, location, onLocationChange }) {
  const [mask, setMask] = useState(10)
  const [availability, setAvailability] = useState(null)
  const [globalObjects, setGlobalObjects] = useState([])
  const [mapMode, setMapMode] = useState('global')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const setLocation = onLocationChange

  useEffect(() => {
    api.communicationGlobeObjects().then((data) => setGlobalObjects(data.objects || [])).catch(() => setGlobalObjects([]))
  }, [])

  const visibleNoradIds = new Set((availability?.satellites || []).map((satellite) => satellite.norad_id))
  const mapSatellites = mapMode === 'visible'
    ? globalObjects.filter((satellite) => visibleNoradIds.has(satellite.norad_id))
    : globalObjects

  useEffect(() => {
    if (!location) return
    setLoading(true)
    setError(null)
    api.communicationAvailability({ lat: location.lat, lon: location.lon, minElevation: mask })
      .then(setAvailability)
      .catch((err) => setError(err.message || 'Could not compute availability'))
      .finally(() => setLoading(false))
  }, [location, mask])

  const visibleByCategory = CORE_ORDER.reduce((groups, category) => {
    const satellites = (availability?.satellites || []).filter(
      (satellite) => (satellite.category || 'Other') === category
    )
    if (satellites.length) groups.push({ category, satellites })
    return groups
  }, [])

  return (
    <div className="availability-stage">
      <article className="panel availability-map-panel">
          <p className="eyebrow">SATELLITE AVAILABILITY BY REGION</p>
          <h2>What's usable from a given location, right now</h2>
          <div className="map-satellite-mode" role="group" aria-label="Satellite map mode">
            <button type="button" className={mapMode === 'global' ? 'active' : ''} onClick={() => setMapMode('global')}>All satellites</button>
            <button type="button" className={mapMode === 'visible' ? 'active' : ''} onClick={() => setMapMode('visible')}>Visible here</button>
          </div>
          <LocationSearch
            presets={presets}
            currentLabel={location?.label || (location ? `${location.lat.toFixed(2)}°, ${location.lon.toFixed(2)}°` : undefined)}
            onSelect={setLocation}
            search={api.locationSearchGlobal}
            searchLabel="Search any place worldwide"
            showCoordinates
          />
          <p className="map-hint">Or click anywhere on the map to check that exact point:</p>
          <CommLocationPicker lat={location?.lat} lon={location?.lon} onPick={setLocation} satellites={mapSatellites} />
          {location && !location.label && (
            <p className="loading-hint">Selected point: {location.lat.toFixed(3)}°, {location.lon.toFixed(3)}°</p>
          )}
          {loading && !availability && <p className="loading-hint">Propagating communication-satellite orbits for this location (SGP4)…</p>}
          {error && <p className="loading-hint" style={{ color: '#ffae5e' }}>{error}</p>}
      </article>

      <div className="availability-right-column">
        {availability && location && (
          <section className="skyplot-section">
            <CommSkyPlot
              satellites={availability.satellites}
              mask={mask}
              onMaskChange={setMask}
              catalogSize={availability.catalog_size}
              location={location}
              onSelect={(sat) => onSelect(fromSkyPlotPoint(sat))}
            />
          </section>
        )}
      </div>

      <article className="panel availability-results" id="availability">
          <p className="eyebrow">SATELLITE VISIBILITY</p>
          <h2>Communication satellites above the horizon</h2>
          {!availability ? (
            <p className="loading-hint">Waiting for a location visibility result…</p>
          ) : (
            <>
              <div className="avail-headline">
                <b>{fmt(availability.visible_count)}</b>
                <span>above {availability.min_elevation_deg}° elevation right now</span>
              </div>
              <div className="country-list">
                {visibleByCategory.map(({ category, satellites }) => (
                  <details className="visibility-group" key={category}>
                    <summary style={{ color: CATEGORY_COLOR[category] }}>
                      <span>{category}</span>
                      <b>{fmt(satellites.length)}</b>
                    </summary>
                    <div className="visibility-satellite-list">
                      {satellites.map((satellite) => (
                        <button
                          type="button"
                          key={satellite.norad_id}
                          onClick={() => onSelect(fromSkyPlotPoint(satellite))}
                        >
                          <span>{satellite.name}</span>
                          <small>NORAD {satellite.norad_id}</small>
                        </button>
                      ))}
                    </div>
                  </details>
                ))}
                </div>
            </>
          )}
      </article>
    </div>
  )
}

function ServiceInfoGrid({ serviceInfo }) {
  if (!serviceInfo) return <p className="loading-hint">Loading category reference data…</p>
  return (
    <div className="service-info-grid">
      {serviceInfo.categories.map((c) => (
        <article key={c.category} className="service-card" style={{ '--sc': CATEGORY_COLOR[c.category] || '#7d8795' }}>
          <header>
            <span className="dot" />
            <h4>{c.category}</h4>
            <span className="status">{c.status}</span>
          </header>
          <p className="full-name">{c.full_name} · {c.operator}</p>
          <div className="service-grid">
            <label>Regime<b>{c.orbital_regime}</b></label>
            <label>Altitude<b>{fmt(c.altitude_km)} km</b></label>
          </div>
          <p className="signals"><b>Fleet:</b> {c.fleet_size_note}</p>
          <p className="accuracy"><b>Services:</b> {c.services.join(', ')}</p>
          {c.source_url && <a href={c.source_url} target="_blank" rel="noreferrer">Source: {c.source}</a>}
        </article>
      ))}
    </div>
  )
}

export default function CommunicationDashboard() {
  const [overview, setOverview] = useState(null)
  const [error, setError] = useState(null)
  const [serviceInfo, setServiceInfo] = useState(null)
  const [selected, setSelected] = useState(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)

  // Observer location is owned at the portal level and shared by the Cesium
  // 3D view and the availability map/sky-plot below, so picking a place in
  // either one (search, preset dropdown, or clicking the map) updates both.
  const [presets, setPresets] = useState([])
  const [location, setLocation] = useState(null)

  useEffect(() => {
    api.communicationOverview()
      .then(setOverview)
      .catch((err) => setError(err.message || 'Could not load live communication-satellite catalog'))
    api.communicationServiceInfo().then(setServiceInfo).catch(() => setServiceInfo(null))
    api.locationPresetsGlobal().then((d) => {
      setPresets(d.presets || [])
      if (d.default) setLocation(d.default)
    }).catch(() => {})
  }, [])

  const categoryBars = useMemo(() => {
    const by = overview?.by_category || {}
    return CORE_ORDER.filter((c) => by[c]).map((c) => ({ label: c, value: by[c], color: CATEGORY_COLOR[c] }))
  }, [overview])

  async function submitSearch(e) {
    e.preventDefault()
    if (!query.trim()) return
    setSearching(true)
    try {
      const r = await api.communicationSatellites({ q: query })
      setResults(r.satellites || [])
      if (r.satellites?.[0]) setSelected(fromSatelliteResult(r.satellites[0]))
    } catch {
      setResults([])
    } finally {
      setSearching(false)
    }
  }

  return (
    <main className="assets-page comm-page">
      <header className="assets-header">
        <a href="#" className="wordmark"><img className="assets-brand-logo" src="/ncgsa-logo.png" alt="NCGSA logo" /><strong>NSO</strong><small>SPACECRAFT OBSERVATORY</small></a>
        <nav>
          <a href="#">← Observatory home</a>
          <PortalMenu />
          <a className="active">04 Communication</a>
        </nav>
        <span className="live-badge" role="status"><i /> LIVE</span>
      </header>

      <section className="assets-intro">
        <div>
          <p className="eyebrow">PORTAL 04</p>
          <h1>Communication <em>Satellite Systems</em></h1>
          <p>Explore the satellites that carry phone calls, internet, TV, and data across the planet. Track live Intelsat, SES, Eutelsat, Telesat, Iridium NEXT, Orbcomm, Globalstar, and amateur-radio objects, inspect their orbital parameters, follow their positions around Earth, and check which are visible from any location. Broadband mega-constellations (Starlink, OneWeb, Kuiper) are covered separately in Portal 01.</p>
        </div>
        <div className="update-note">
          {error ? error : overview?.updated_at ? `Last refreshed ${new Date(overview.updated_at).toLocaleString()}` : 'Connecting to CelesTrak'}
          <br /><span>Live SGP4-propagated positions</span>
        </div>
      </section>

      <section className="command-grid">
        <article className="globe-card panel">
          <div className="panel-head">
            <div><p className="eyebrow">SATELLITE CATEGORY 3D ORBITS · CESIUM</p><h2>Communication satellites around Earth</h2></div>
            <span>Live SGP4-propagated positions, colored by category</span>
          </div>
          <CommGlobe
            selected={selected}
            onSelect={(o) => setSelected(fromGlobePoint(o))}
            presets={presets}
            location={location}
            onLocationChange={setLocation}
          />
        </article>
        <aside className="panel profile-panel">
          <ObjectProfile item={selected} onClose={() => setSelected(null)} />
        </aside>
      </section>

      <AvailabilityPanel onSelect={setSelected} presets={presets} location={location} onLocationChange={setLocation} />

      <section id="breakdown" className="snapshot">
        <div className="section-title">
          <p className="eyebrow">CATEGORY BREAKDOWN</p>
          <h2>Satellites per communication category</h2>
          <span>Classified communication satellite inventory</span>
        </div>
        <div className="snapshot-grid">
          <article className="panel chart-card">
            <h3>Satellites by category</h3>
            <BarChart data={categoryBars} />
          </article>
          <article id="sources" className="panel search-card nav-search-card">
            <p className="eyebrow">COMMUNICATION SATELLITE SEARCH</p>
            <h2>Locate a communication satellite</h2>
            <form onSubmit={submitSearch}>
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search name or NORAD ID…" />
              <button>{searching ? 'Searching…' : 'Search'}</button>
            </form>
            {results.length > 0 && (
              <div className="search-results">
                {results.slice(0, 8).map((s) => (
                  <button type="button" key={s.norad_id} onClick={() => setSelected(fromSatelliteResult(s))}>
                    {s.name}<span style={{ color: CATEGORY_COLOR[s.category] }}>{s.category} · NORAD {s.norad_id}</span>
                  </button>
                ))}
              </div>
            )}
          </article>
        </div>
      </section>

      <section id="service-info" className="activity-grid" style={{ gridTemplateColumns: '1fr' }}>
        <article className="panel activity" style={{ gridColumn: '1 / -1' }}>
          <p className="eyebrow">FLEET & SERVICE INFO</p>
          <h2>Published operator specifications</h2>
          <p style={{ marginBottom: 14 }}>Published fleet and service characteristics, from each operator's own site — not live telemetry.</p>
          <ServiceInfoGrid serviceInfo={serviceInfo} />
        </article>
      </section>

      <footer className="assets-footer">
        Data attribution: <a href="https://celestrak.org/" target="_blank" rel="noreferrer">CelesTrak GP data</a> (GROUP=intelsat, ses, eutelsat, telesat, iridium-NEXT, orbcomm, globalstar, amateur) ·
        Reference specs: Intelsat, SES, Eutelsat, Telesat, Iridium, ORBCOMM, Globalstar and AMSAT official sites ·
        Live data is cached server-side for up to 5 minutes. Values marked "Data unavailable" require a compatible authoritative source connection.
      </footer>
    </main>
  )
}
