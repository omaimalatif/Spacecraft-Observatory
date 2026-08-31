import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import PortalMenu from './PortalMenu.jsx'
import LocationSearch from './LocationSearch.jsx'
import EoLocationPicker from './EoLocationPicker.jsx'
import EoSkyPlot from './EoSkyPlot.jsx'
import { CATEGORY_COLOR, CATEGORY_ORDER } from './eoCategories.js'

const EoGlobe = lazy(() => import('./EoGlobe.jsx'))

const fmt = (n) => n == null ? 'Data unavailable' : new Intl.NumberFormat().format(n)

// Same colors EoGlobe.jsx uses for the on-globe dots, reused here so the KPI
// cards visually match what's plotted below.
const HAZARD_ACCENTS = {
  'Fire Detection': '#ff8a5c',
  'Storm & Weather Tracking': '#ffd166',
  'Flood & Precipitation Monitoring': '#5ec8ff',
  'General Earth Observation': '#8fe3c7',
}

function LiveClock() {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return <span className="live-clock">{now.toISOString().slice(0, 19).replace('T', ' ')} UTC</span>
}

function fromGlobePoint(o) {
  return { ...o, category: o.hazard_focus, hasLivePosition: true }
}
function fromSkyPlotPoint(s) {
  return { ...s, hasLivePosition: false }
}
function fromSatelliteResult(s) {
  return { ...s, hasLivePosition: false }
}

function AvailabilityPanel({ onSelect, presets, location, onLocationChange }) {
  const [mask, setMask] = useState(10)
  const [availability, setAvailability] = useState(null)
  const [globalObjects, setGlobalObjects] = useState([])
  const [globalObjectsError, setGlobalObjectsError] = useState(null)
  const [mapMode, setMapMode] = useState('global')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const setLocation = onLocationChange

  useEffect(() => {
    api.earthObservationGlobeObjects().then((data) => setGlobalObjects((data.objects || []).map((o) => ({ ...o, category: o.hazard_focus }))))
      .catch((err) => { setGlobalObjects([]); setGlobalObjectsError(err.message || 'Could not load live satellite positions') })
  }, [])

  const visibleNoradIds = new Set((availability?.satellites || []).map((satellite) => satellite.norad_id))
  const mapSatellites = mapMode === 'visible'
    ? globalObjects.filter((satellite) => visibleNoradIds.has(satellite.norad_id))
    : globalObjects

  useEffect(() => {
    if (!location) return
    setLoading(true)
    setError(null)
    api.earthObservationAvailability({ lat: location.lat, lon: location.lon, minElevation: mask })
      .then(setAvailability)
      .catch((err) => setError(err.message || 'Could not compute availability'))
      .finally(() => setLoading(false))
  }, [location, mask])

  const visibleByCategory = CATEGORY_ORDER.reduce((groups, category) => {
    const satellites = (availability?.satellites || []).filter(
      (satellite) => (satellite.category || 'General Earth Observation') === category
    )
    if (satellites.length) groups.push({ category, satellites })
    return groups
  }, [])

  return (
    <div className="availability-stage">
      <article className="panel availability-map-panel">
          <p className="eyebrow">SATELLITE AVAILABILITY BY REGION</p>
          <h2>What's overhead from a given location, right now</h2>
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
          <EoLocationPicker lat={location?.lat} lon={location?.lon} onPick={setLocation} satellites={mapSatellites} />
          {location && !location.label && (
            <p className="loading-hint">Selected point: {location.lat.toFixed(3)}°, {location.lon.toFixed(3)}°</p>
          )}
          {globalObjectsError && <p className="loading-hint" style={{ color: '#ffae5e' }}>{globalObjectsError} — the map will only show the current search location until this is resolved.</p>}
          {loading && !availability && <p className="loading-hint">Propagating EO satellite orbits for this location (SGP4)…</p>}
          {error && <p className="loading-hint" style={{ color: '#ffae5e' }}>{error}</p>}
      </article>

      <div className="availability-right-column">
        {availability && location && (
          <section className="skyplot-section">
            <EoSkyPlot
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
          <h2>Earth-observation satellites above the horizon</h2>
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

function ServiceInfoGrid({ serviceInfo, error }) {
  if (error) return <p className="loading-hint" style={{ color: '#ffae5e' }}>{error}</p>
  if (!serviceInfo) return <p className="loading-hint">Loading category reference data…</p>
  return (
    <div className="service-info-grid">
      {serviceInfo.categories.map((c) => {
        const dot = CATEGORY_COLOR[c.category]
        return (
          <article key={c.category} className="service-card" style={{ '--sc': dot || '#7d8795' }}>
            <header>
              <span className="dot" />
              <h4>{c.category}</h4>
            </header>
            <p className="full-name">{c.full_name}</p>
            <p className="signals">{c.description}</p>
            {c.example_missions?.length > 0 && (
              <p className="accuracy"><b>Example missions:</b> {c.example_missions.join(', ')}</p>
            )}
            {c.source_url && <a href={c.source_url} target="_blank" rel="noreferrer">Source: {c.source}</a>}
          </article>
        )
      })}
    </div>
  )
}

export default function EarthObservation() {
  const [types, setTypes] = useState(null)
  const [typesError, setTypesError] = useState(null)
  const [selected, setSelected] = useState(null)
  const [serviceInfo, setServiceInfo] = useState(null)
  const [serviceInfoError, setServiceInfoError] = useState(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)

  // Observer location is owned at the portal level and shared across the
  // availability map/sky-plot below, so picking a place (search, preset
  // dropdown, or clicking the map) updates all of them together — same
  // pattern as every other satellite-tracking portal in this app.
  const [presets, setPresets] = useState([])
  const [location, setLocation] = useState(null)

  useEffect(() => {
    api.earthObservationTypes()
      .then((d) => { setTypes(d); setTypesError(null) })
      .catch((err) => setTypesError(err.message || 'Data unavailable'))
    api.earthObservationServiceInfo().then(setServiceInfo)
      .catch((err) => setServiceInfoError(err.message || 'Could not load reference data'))
    api.locationPresetsGlobal().then((d) => {
      setPresets(d.presets || [])
      if (d.default) setLocation(d.default)
    }).catch(() => {})
  }, [])

  const hazardBars = useMemo(() => {
    if (!types) return []
    return types.types.map((t) => ({ label: t.label, value: t.total, color: HAZARD_ACCENTS[t.label] }))
  }, [types])

  async function submitSearch(e) {
    e.preventDefault()
    if (!query.trim()) return
    setSearching(true)
    try {
      const r = await api.earthObservationSatellites({ q: query })
      setResults(r.satellites || [])
      if (r.satellites?.[0]) setSelected(fromSatelliteResult(r.satellites[0]))
    } catch {
      setResults([])
    } finally {
      setSearching(false)
    }
  }

  return (
    <main className="eo-page">
      <header className="eo-header">
        <a href="#" className="wordmark"><img className="assets-brand-logo" src="/ncgsa-logo.png" alt="NCGSA logo" /><span>NCGSA</span><small>SPACECRAFT OBSERVATORY</small></a>
        <nav>
          <a href="#">← Observatory home</a>
          <PortalMenu />
          <a className="active">02 Earth Observation Satellites</a>
        </nav>
        <div className="eo-header-right">
          <LiveClock />
          <span className="live-badge" role="status"><i /> LIVE</span>
        </div>
      </header>

      <section className="eo-intro">
        <div>
          <p className="eyebrow">PORTAL 02 / MISSION OVERVIEW</p>
          <h1>Earth Observation <em>Satellites</em></h1>
          <p>
            Which satellites are watching Earth for hazards — live 3D orbital positions of the
            spacecraft that detect fires, storms, floods and other events. Track live Fire
            Detection, Storm &amp; Weather Tracking, and Flood &amp; Precipitation Monitoring
            satellites, inspect their orbital parameters, and check which are visible from any
            location.
          </p>
        </div>
      </section>

      <section className="eo-kpis eo-hazard-kpis">
        {typesError ? (
          <article style={{ gridColumn: '1 / -1' }}><span>Satellite categories</span><strong className="unavailable">{typesError}</strong></article>
        ) : !types ? (
          <p className="eo-empty">Loading satellite categories…</p>
        ) : (
          <>
            <article style={{ '--accent': '#79d8ff' }}>
              <span>EO satellites tracked</span>
              <strong>{fmt(types.total)}</strong>
              <small>CelesTrak resource + weather groups</small>
            </article>
            {types.types.map((t) => (
              <article key={t.label} style={{ '--accent': HAZARD_ACCENTS[t.label] }}>
                <span>{t.label}</span>
                <strong>{fmt(t.total)}</strong>
                <small>{fmt(t.active)} active</small>
              </article>
            ))}
          </>
        )}
      </section>

      <section className="eo-globe-section">
        <article className="globe-card panel">
          <div className="panel-head">
            <div><p className="eyebrow">ORBITAL VIEW · CESIUM 3D</p><h2>Earth observation satellites in orbit</h2></div>
            <span title="Live SGP4-propagated positions, CelesTrak GROUP=resource + GROUP=weather">Live SGP4-propagated positions</span>
          </div>
          <Suspense fallback={<div className="globe-loading" role="status">Loading orbital view…</div>}>
            <EoGlobe
              selected={selected}
              onSelect={(o) => setSelected(fromGlobePoint(o))}
              onClose={() => setSelected(null)}
              location={location}
              onLocationChange={setLocation}
              presets={presets}
            />
          </Suspense>
        </article>
      </section>

      <AvailabilityPanel onSelect={setSelected} presets={presets} location={location} onLocationChange={setLocation} />

      <section id="breakdown" className="snapshot">
        <div className="section-title">
          <p className="eyebrow">HAZARD-FOCUS BREAKDOWN</p>
          <h2>Satellites per hazard focus</h2>
          <span>Classified Earth-observation satellite inventory</span>
        </div>
        <div className="snapshot-grid">
          <article className="panel chart-card">
            <h3>Satellites by hazard focus</h3>
            <div className="bar-chart">
              {hazardBars.map((x) => {
                const max = Math.max(...hazardBars.map((b) => b.value), 1)
                return (
                  <div className="bar-row" key={x.label}>
                    <span>{x.label}</span>
                    <div className="bar-track"><i style={{ width: `${(x.value / max) * 100}%`, background: x.color ? `linear-gradient(90deg, ${x.color}66, ${x.color})` : undefined }} /></div>
                    <b>{fmt(x.value)}</b>
                  </div>
                )
              })}
            </div>
          </article>
          <article id="sources" className="panel search-card nav-search-card">
            <p className="eyebrow">EARTH OBSERVATION SATELLITE SEARCH</p>
            <h2>Locate an Earth-observation satellite</h2>
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
          <p className="eyebrow">HAZARD FOCUS CONTEXT</p>
          <h2>What each hazard-focus category means</h2>
          <p style={{ marginBottom: 14 }}>General mission-family context from public agency pages — not live telemetry.</p>
          <ServiceInfoGrid serviceInfo={serviceInfo} error={serviceInfoError} />
        </article>
      </section>

      <footer className="eo-footer">
        Data attribution: <a href="https://celestrak.org/" target="_blank" rel="noreferrer">CelesTrak GP</a> (live satellite positions, SGP4-propagated) ·{' '}
        <a href="https://celestrak.org/satcat/" target="_blank" rel="noreferrer">CelesTrak SATCAT</a> (active/inactive status). Hazard-focus categories are a
        best-effort classification from each satellite's mission name against known patterns (e.g. TERRA/AQUA/SUOMI NPP → Fire Detection) —
        not an authoritative purpose registry. Indicative subset of CelesTrak's own mission-category groups, not a complete EO satellite census.
      </footer>
    </main>
  )
}
