import { useEffect, useMemo, useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from 'react-leaflet'
import { api } from '../api.js'
import PortalMenu from './PortalMenu.jsx'

const fmt = (n) => n == null ? 'Unavailable' : new Intl.NumberFormat().format(n)

const PAKISTAN_BBOX = { west: 60.5, south: 23.5, east: 77.9, north: 37.2 }
const PAKISTAN_BBOX_STR = `${PAKISTAN_BBOX.west},${PAKISTAN_BBOX.south},${PAKISTAN_BBOX.east},${PAKISTAN_BBOX.north}`
const PAKISTAN_CENTER = [30.3753, 69.3451]
const WORLD_CENTER = [15, 10]

const HAZARD_COLORS = {
  wildfires: '#ff6b4a', volcanoes: '#c98cff', severeStorms: '#ffd166',
  floods: '#5ec8ff', drought: '#e0a458', default: '#9fb8c7',
}

function inBbox(lat, lon, bbox) {
  return lat >= bbox.south && lat <= bbox.north && lon >= bbox.west && lon <= bbox.east
}

// Flies the map to a new center when the Pakistan/Global toggle changes.
function FlyTo({ center, zoom }) {
  const map = useMap()
  useEffect(() => { map.flyTo(center, zoom, { duration: 0.8 }) }, [center, zoom]) // eslint-disable-line react-hooks/exhaustive-deps
  return null
}

function LiveClock() {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return <span className="live-clock">{now.toISOString().slice(0, 19).replace('T', ' ')} UTC</span>
}

function StatusDot({ status }) {
  const cls = status === 'ONLINE' ? 'ok' : status === 'NOT CONFIGURED' || status === 'NOT CONNECTED' ? 'off' : 'warn'
  return <span className={`status-dot ${cls}`}><i />{status}</span>
}

export default function EarthObservation() {
  const [scope, setScope] = useState('global') // 'global' | 'pakistan'
  const [layers, setLayers] = useState([])
  const [activeBase, setActiveBase] = useState('modis-terra-truecolor')
  const [showAerosol, setShowAerosol] = useState(false)
  const [showFires, setShowFires] = useState(true)
  const [showHazards, setShowHazards] = useState(true)

  const [events, setEvents] = useState([])
  const [eventsError, setEventsError] = useState(null)
  const [fires, setFires] = useState([])
  const [firesMeta, setFiresMeta] = useState(null)
  const [firesError, setFiresError] = useState(null)
  const [satellites, setSatellites] = useState(null)
  const [status, setStatus] = useState(null)
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.earthObservationLayers().then((d) => setLayers(d.layers || [])).catch(() => setLayers([]))
    api.earthObservationSatellites().then(setSatellites).catch(() => setSatellites(null))
    api.earthObservationStatus().then(setStatus).catch(() => setStatus(null))
  }, [])

  useEffect(() => {
    setLoading(true)
    api.earthObservationEvents()
      .then((d) => { setEvents(d.events || []); setEventsError(null) })
      .catch((err) => setEventsError(err.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const bbox = scope === 'pakistan' ? PAKISTAN_BBOX_STR : 'world'
    api.earthObservationFires(bbox)
      .then((d) => { setFires(d.fires || []); setFiresMeta(d); setFiresError(null) })
      .catch((err) => { setFires([]); setFiresMeta(null); setFiresError(err.message) })
  }, [scope])

  const visibleEvents = useMemo(() => {
    if (scope !== 'pakistan') return events
    return events.filter((e) => {
      const geoArr = e.geometry || []
      const geo = geoArr[geoArr.length - 1]
      const coords = geo?.coordinates
      if (!coords) return false
      const [lon, lat] = geo.type === 'Point' ? coords : [coords[0]?.[0]?.[0] ?? coords[0], coords[0]?.[0]?.[1] ?? coords[1]]
      return typeof lat === 'number' && typeof lon === 'number' && inBbox(lat, lon, PAKISTAN_BBOX)
    })
  }, [events, scope])

  const activeLayer = layers.find((l) => l.id === activeBase)
  const aerosolLayer = layers.find((l) => l.id === 'modis-terra-aerosol')
 // GIBS daily layers need ~1-2 days for a satellite to complete full global
// coverage — requesting "today" shows real but incomplete orbital swaths
// (black gaps between passes) rather than a finished picture. Defaulting
// 2 days back matches NASA's own Worldview convention for reliable coverage.
const imageryDate = useMemo(() => {
  const d = new Date()
  d.setUTCDate(d.getUTCDate() - 2)
  return d.toISOString().slice(0, 10)
}, [])
  const highConfidence = firesMeta?.high_confidence_count ?? null
  const notConnected = ['Land Cover / NDVI', 'Ocean (SST, chlorophyll)', 'Copernicus Sentinel imagery', 'USGS Landsat historical', 'NOAA weather imagery']

  return (
    <main className="eo-page">
      <header className="eo-header">
        <a href="#" className="wordmark"><img className="assets-brand-logo" src="/ncgsa-logo.png" alt="NCGSA logo" /><span>NCGSA</span><small>SPACECRAFT OBSERVATORY</small></a>
        <nav>
          <a href="#">← Observatory home</a>
          <PortalMenu />
          <a className="active">02 Earth Observation</a>
        </nav>
        <div className="eo-header-right">
          <LiveClock />
          <span className="live-badge" role="status"><i /> LIVE</span>
        </div>
      </header>

      <section className="eo-intro">
        <div>
          <p className="eyebrow">PORTAL 02 / MISSION OVERVIEW</p>
          <h1>Earth <em>Observation</em> Missions</h1>
          <p>Monitoring Earth's surface, atmosphere and active hazards through imagery, fires and event data.</p>
        </div>
        <div className="eo-scope-toggle">
          <button className={scope === 'global' ? 'active' : ''} onClick={() => setScope('global')}>GLOBAL</button>
          <button className={scope === 'pakistan' ? 'active' : ''} onClick={() => setScope('pakistan')}>PAKISTAN</button>
        </div>
      </section>

      <section className="eo-kpis">
        <article><span>Open hazard events</span><strong className={eventsError ? 'unavailable' : ''}>{eventsError ? 'Unavailable' : fmt(visibleEvents.length)}</strong></article>
        <article><span>Active fires (24h)</span><strong className={firesError ? 'unavailable' : ''}>{firesError ? firesError : fmt(fires.length)}</strong></article>
        <article><span>High-confidence fires</span><strong className={highConfidence == null ? 'unavailable' : ''}>{fmt(highConfidence)}</strong><small>Confidence ≥ 80% or "high"</small></article>
        <article><span>EO satellites tracked</span><strong className={satellites?.total == null ? 'unavailable' : ''}>{fmt(satellites?.total)}</strong></article>
        <article><span>Imagery layers connected</span><strong>{fmt(layers.length)}</strong></article>
      </section>

      <section className="eo-command-grid">
        <article className="eo-map-card panel">
          <div className="panel-head">
            <div><p className="eyebrow">LIVE EARTH VIEW</p><h2>{scope === 'pakistan' ? 'Pakistan' : 'Global'} — {activeLayer?.label || 'Imagery'}</h2></div>
            <span>{activeLayer ? activeLayer.label : ''}</span>
          </div>
          <div className="eo-map-stage">
            <MapContainer center={scope === 'pakistan' ? PAKISTAN_CENTER : WORLD_CENTER} zoom={scope === 'pakistan' ? 5 : 3} minZoom={2} style={{ height: '100%', width: '100%' }} worldCopyJump>
              <FlyTo center={scope === 'pakistan' ? PAKISTAN_CENTER : WORLD_CENTER} zoom={scope === 'pakistan' ? 5 : 3} />
              {activeLayer && (
                <TileLayer
                  url={activeLayer.tile_url_template.replace('{time}', imageryDate)}
                  attribution={`&copy; ${activeLayer.source}`}
                  maxNativeZoom={activeLayer.max_zoom}
                  tileSize={256}
                />
              )}
              {showAerosol && aerosolLayer && (
                <TileLayer
                  url={aerosolLayer.tile_url_template.replace('{time}', imageryDate)}
                  attribution={`&copy; ${aerosolLayer.source}`}
                  maxNativeZoom={aerosolLayer.max_zoom}
                  opacity={0.65}
                />
              )}
              {showFires && fires.map((f, i) => (
                <CircleMarker key={i} center={[f.lat, f.lon]} radius={3} pathOptions={{ color: '#ff6b4a', fillColor: '#ff6b4a', fillOpacity: 0.9, weight: 0 }}>
                  <Popup>
                    <b>Active fire detection</b><br />
                    Lat/Lon: {f.lat.toFixed(3)}, {f.lon.toFixed(3)}<br />
                    Acquired: {f.acq_date} {f.acq_time} UTC<br />
                    Satellite: {f.satellite} / {f.instrument}<br />
                    Confidence: {f.confidence}<br />
                    {f.frp != null && <>FRP: {f.frp} MW<br /></>}
                  </Popup>
                </CircleMarker>
              ))}
              {showHazards && visibleEvents.map((e) => {
                const geoArr = e.geometry || []
                const geo = geoArr[geoArr.length - 1]
                if (!geo || geo.type !== 'Point') return null
                const [lon, lat] = geo.coordinates
                const cat = e.categories?.[0]?.id || 'default'
                return (
                  <CircleMarker key={e.id} center={[lat, lon]} radius={5}
                    pathOptions={{ color: HAZARD_COLORS[cat] || HAZARD_COLORS.default, fillColor: HAZARD_COLORS[cat] || HAZARD_COLORS.default, fillOpacity: 0.85, weight: 1.5 }}
                    eventHandlers={{ click: () => setSelected(e) }}>
                    <Popup>
                      <b>{e.title}</b><br />
                      Category: {e.categories?.[0]?.title || 'Unknown'}<br />
                      Detected: {geo.date ? new Date(geo.date).toLocaleString() : '—'}<br />
                      {e.sources?.[0] && <a href={e.sources[0].url} target="_blank" rel="noreferrer">Source</a>}
                    </Popup>
                  </CircleMarker>
                )
              })}
            </MapContainer>
          </div>
          <p className="eo-map-note">Imagery date: {imageryDate} (2-day lag for full global coverage) · Fire window: last 24h · ...</p>
        </article>

        <aside className="panel eo-layer-panel">
          <p className="eyebrow">LAYER CONTROLS</p>
          <h3>Base imagery</h3>
          {layers.filter((l) => l.category === 'base').map((l) => (
            <button key={l.id} className={`eo-layer-btn ${activeBase === l.id ? 'active' : ''}`} onClick={() => setActiveBase(l.id)}>
              {l.label}
            </button>
          ))}
          <h3>Atmosphere</h3>
          <label className="eo-toggle"><input type="checkbox" checked={showAerosol} onChange={(e) => setShowAerosol(e.target.checked)} /> Aerosol optical depth</label>
          <h3>Hazards</h3>
          <label className="eo-toggle"><input type="checkbox" checked={showFires} onChange={(e) => setShowFires(e.target.checked)} /> Active fires (FIRMS)</label>
          <label className="eo-toggle"><input type="checkbox" checked={showHazards} onChange={(e) => setShowHazards(e.target.checked)} /> Hazard events (EONET)</label>
          <h3>Not yet connected</h3>
          <ul className="eo-not-connected">
            {notConnected.map((n) => <li key={n}>{n}</li>)}
          </ul>
        </aside>
      </section>

      <section className="eo-lower-grid">
        <article className="panel">
          <p className="eyebrow">HAZARD EVENTS</p>
          <h2>Open events {scope === 'pakistan' ? 'in Pakistan' : 'worldwide'}</h2>
          {loading ? <p className="eo-empty">Loading…</p> : eventsError ? <p className="eo-empty">{eventsError}</p> : visibleEvents.length === 0 ? (
            <p className="eo-empty">No open hazard events {scope === 'pakistan' ? 'in Pakistan' : ''} right now.</p>
          ) : (
            <div className="eo-event-list">
              {visibleEvents.slice(0, 8).map((e) => (
                <button key={e.id} className="eo-event-row" onClick={() => setSelected(e)}>
                  <span className="dot" style={{ background: HAZARD_COLORS[e.categories?.[0]?.id] || HAZARD_COLORS.default }} />
                  <span className="name">{e.title}</span>
                  <span className="cat">{e.categories?.[0]?.title}</span>
                </button>
              ))}
            </div>
          )}
        </article>

        <article className="panel">
          <p className="eyebrow">DATA SERVICES</p>
          <h2>Source status</h2>
          {status ? (
            <ul className="eo-status-list">
              {status.services.map((s) => (
                <li key={s.name}>
                  <a href={s.url} target="_blank" rel="noreferrer">{s.name}</a>
                  <StatusDot status={s.status} />
                </li>
              ))}
            </ul>
          ) : <p className="eo-empty">Checking service status…</p>}
          <small>Statuses reflect the most recent real request this session — nothing here is simulated.</small>
        </article>
      </section>

      {selected && (
        <div className="eo-drawer" onClick={() => setSelected(null)}>
          <div className="eo-drawer-panel" onClick={(e) => e.stopPropagation()}>
            <button className="close" onClick={() => setSelected(null)}>×</button>
            <span className="eyebrow">EVENT DETAIL</span>
            <h3>{selected.title}</h3>
            <p>{selected.categories?.[0]?.title}</p>
            {selected.sources?.[0] && <a href={selected.sources[0].url} target="_blank" rel="noreferrer">View source →</a>}
          </div>
        </div>
      )}

      <footer className="eo-footer">
        Data attribution: <a href="https://www.earthdata.nasa.gov/gibs" target="_blank" rel="noreferrer">NASA GIBS</a> · <a href="https://firms.modaps.eosdis.nasa.gov/" target="_blank" rel="noreferrer">NASA FIRMS</a> · <a href="https://eonet.gsfc.nasa.gov/" target="_blank" rel="noreferrer">NASA EONET</a>. Fire and hazard data reflect NASA's near-real-time feeds and may lag actual events by minutes to hours.
      </footer>
    </main>
  )
}
