
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import NavGlobe, { CONSTELLATION_COLOR, CONSTELLATION_ORDER } from './NavGlobe.jsx'
import SkyPlot from './SkyPlot.jsx'
import LocationSearch from './LocationSearch.jsx'
import WorldLocationPicker from './WorldLocationPicker.jsx'
import PortalMenu from './PortalMenu.jsx'

const fmt = (n) => n == null ? 'Data unavailable' : new Intl.NumberFormat().format(n)
const num = (n, digits = 0) => Number.isFinite(Number(n)) ? Number(n).toFixed(digits) : '—'

const CORE_ORDER = [...CONSTELLATION_ORDER, 'Other']

function fromSkyPlotPoint(s) {
  return {
    name: s.name, norad_id: s.norad_id, constellation: s.constellation, regime: null,
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
    name: o.name, norad_id: o.norad_id, constellation: o.constellation, regime: o.regime,
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
    name: s.name, norad_id: s.norad_id, cospar_id: s.cospar_id, constellation: s.constellation,
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
        <label>Constellation<b style={{ color: CONSTELLATION_COLOR[item.constellation] }}>{item.constellation}</b></label>
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
    api.navigationGlobeObjects().then((data) => setGlobalObjects(data.objects || [])).catch(() => setGlobalObjects([]))
  }, [])

  const visibleNoradIds = new Set((availability?.satellites || []).map((satellite) => satellite.norad_id))
  const mapSatellites = mapMode === 'visible'
    ? globalObjects.filter((satellite) => visibleNoradIds.has(satellite.norad_id))
    : globalObjects

  useEffect(() => {
    if (!location) return
    setLoading(true)
    setError(null)
    api.navigationAvailability({ lat: location.lat, lon: location.lon, minElevation: mask })
      .then(setAvailability)
      .catch((err) => setError(err.message || 'Could not compute availability'))
      .finally(() => setLoading(false))
  }, [location, mask])

  const visibleByConstellation = CORE_ORDER.reduce((groups, constellation) => {
    const satellites = (availability?.satellites || []).filter(
      (satellite) => (satellite.constellation || 'Other') === constellation
    )
    if (satellites.length) groups.push({ constellation, satellites })
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
          <WorldLocationPicker lat={location?.lat} lon={location?.lon} onPick={setLocation} satellites={mapSatellites} />
          {location && !location.label && (
            <p className="loading-hint">Selected point: {location.lat.toFixed(3)}°, {location.lon.toFixed(3)}°</p>
          )}
          {loading && !availability && <p className="loading-hint">Propagating GNSS orbits for this location (SGP4)…</p>}
          {error && <p className="loading-hint" style={{ color: '#ffae5e' }}>{error}</p>}
      </article>

      <div className="availability-right-column">
        {availability && location && (
          <section className="skyplot-section">
            <SkyPlot
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
          <h2>GNSS satellites above the horizon</h2>
          {!availability ? (
            <p className="loading-hint">Waiting for a location visibility result…</p>
          ) : (
            <>
              <div className="avail-headline">
                <b>{fmt(availability.visible_count)}</b>
                <span>above {availability.min_elevation_deg}° elevation right now</span>
              </div>
              <div className="country-list">
                {visibleByConstellation.map(({ constellation, satellites }) => (
                  <details className="visibility-group" key={constellation}>
                    <summary style={{ color: CONSTELLATION_COLOR[constellation] }}>
                      <span>{constellation}</span>
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
  if (!serviceInfo) return <p className="loading-hint">Loading constellation reference data…</p>
  return (
    <div className="service-info-grid">
      {serviceInfo.constellations.map((c) => (
        <article key={c.constellation} className="service-card" style={{ '--sc': CONSTELLATION_COLOR[c.constellation] || '#7d8795' }}>
          <header>
            <span className="dot" />
            <h4>{c.constellation}</h4>
            <span className="status">{c.status}</span>
          </header>
          <p className="full-name">{c.full_name}</p>
          <div className="service-grid">
            <label>Operator<b>{c.operator}</b></label>
            <label>Regime<b>{c.orbital_regime}</b></label>
            <label>Altitude<b>{fmt(c.altitude_km)} km</b></label>
            <label>Planes<b>{typeof c.orbital_planes === 'number' ? fmt(c.orbital_planes) : c.orbital_planes}</b></label>
          </div>
          <p className="signals"><b>Signals:</b> {c.signals.join(', ')}</p>
          <p className="accuracy"><b>Stated accuracy:</b> {c.stated_accuracy}</p>
        </article>
      ))}
    </div>
  )
}

export default function NavigationDashboard() {
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
    api.navigationOverview()
      .then(setOverview)
      .catch((err) => setError(err.message || 'Could not load live GNSS catalog'))
    api.navigationServiceInfo().then(setServiceInfo).catch(() => setServiceInfo(null))
    api.locationPresetsGlobal().then((d) => {
      setPresets(d.presets || [])
      if (d.default) setLocation(d.default)
    }).catch(() => {})
  }, [])

  const constellationBars = useMemo(() => {
    const by = overview?.by_constellation || {}
    return CORE_ORDER.filter((c) => by[c]).map((c) => ({ label: c, value: by[c], color: CONSTELLATION_COLOR[c] }))
  }, [overview])

  async function submitSearch(e) {
    e.preventDefault()
    if (!query.trim()) return
    setSearching(true)
    try {
      const r = await api.navigationSatellites({ q: query })
      setResults(r.satellites || [])
      if (r.satellites?.[0]) setSelected(fromSatelliteResult(r.satellites[0]))
    } catch {
      setResults([])
    } finally {
      setSearching(false)
    }
  }

  return (
    <main className="assets-page nav-page">
      <header className="assets-header">
        <a href="#" className="wordmark"><img className="assets-brand-logo" src="/ncgsa-logo.png" alt="NCGSA logo" /><strong>NSO</strong><small>SPACECRAFT OBSERVATORY</small></a>
        <nav>
          <a href="#">← Observatory home</a>
          <PortalMenu />
          <a className="active">03 Navigation Systems</a>
        </nav>
        <span className="live-badge" role="status"><i /> LIVE</span>
      </header>

      <section className="assets-intro">
        <div>
          <p className="eyebrow">PORTAL 03</p>
          <h1>Navigation <em>Satellite Systems</em></h1>
          <p>Monitor the satellite systems that support positioning, navigation, and timing around the world. Explore live GPS, Galileo, GLONASS, BeiDou, QZSS, and NavIC objects, inspect their orbital parameters, follow their positions around Earth, and check which satellites are visible from any location.</p>
        </div>
        <div className="update-note">
          {error ? error : overview?.updated_at ? `Last refreshed ${new Date(overview.updated_at).toLocaleString()}` : 'Connecting to CelesTrak'}
          <br /><span>Live SGP4-propagated positions</span>
        </div>
      </section>

      <section className="command-grid">
        <article className="globe-card panel">
          <div className="panel-head">
            <div><p className="eyebrow">CONSTELLATION 3D ORBITS · CESIUM</p><h2>GNSS satellites around Earth</h2></div>
            <span>Live SGP4-propagated positions, colored by constellation</span>
          </div>
          <NavGlobe
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
          <p className="eyebrow">CONSTELLATION BREAKDOWN</p>
          <h2>Satellites per GNSS system</h2>
          <span>Classified navigation satellite inventory</span>
        </div>
        <div className="snapshot-grid">
          <article className="panel chart-card">
            <h3>Satellites by constellation</h3>
            <BarChart data={constellationBars} />
          </article>
          <article id="sources" className="panel search-card nav-search-card">
            <p className="eyebrow">GNSS SATELLITE SEARCH</p>
            <h2>Locate a navigation satellite</h2>
            <form onSubmit={submitSearch}>
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search name or NORAD ID…" />
              <button>{searching ? 'Searching…' : 'Search'}</button>
            </form>
            {results.length > 0 && (
              <div className="search-results">
                {results.slice(0, 8).map((s) => (
                  <button type="button" key={s.norad_id} onClick={() => setSelected(fromSatelliteResult(s))}>
                    {s.name}<span style={{ color: CONSTELLATION_COLOR[s.constellation] }}>{s.constellation} · NORAD {s.norad_id}</span>
                  </button>
                ))}
              </div>
            )}
          </article>
        </div>
      </section>

      <section id="service-info" className="activity-grid" style={{ gridTemplateColumns: '1fr' }}>
        <article className="panel activity" style={{ gridColumn: '1 / -1' }}>
          <p className="eyebrow">SYSTEM ACCURACY & SERVICE INFO</p>
          <h2>Published constellation specifications</h2>
          <p style={{ marginBottom: 14 }}>Published constellation specifications and service characteristics.</p>
          <ServiceInfoGrid serviceInfo={serviceInfo} />
        </article>
      </section>

      <footer className="assets-footer">
        Data attribution: <a href="https://celestrak.org/" target="_blank" rel="noreferrer">CelesTrak GP data</a> (GROUP=gnss) ·
        Reference specs: <a href="https://www.gps.gov/" target="_blank" rel="noreferrer">GPS.gov</a>, <a href="https://www.gsc-europa.eu/" target="_blank" rel="noreferrer">ESA/EUSPA Navipedia</a>, BeiDou/GLONASS/QZSS/NavIC official ICDs ·
        Live data is cached server-side for up to 2 hours (CelesTrak refresh cadence). Values marked "Data unavailable" require a compatible authoritative source connection.
      </footer>
    </main>
  )
}