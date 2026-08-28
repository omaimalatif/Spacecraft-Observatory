import { useEffect, useRef, useState } from 'react'
import { MapContainer, TileLayer, Marker, Popup, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import { api } from '../api.js'
import LocationSearch from './LocationSearch.jsx'

// The default observation point: Institute of Space Technology, Islamabad.
// Matches backend/app/routers/location.py PRESETS[0] so the default view is
// the same whether the live presets call has resolved yet or not.
const IST_LOCATION = {
  lat: 33.52038,
  lon: 73.17373,
  label: 'Institute of Space Technology, Islamabad',
  name: 'Institute of Space Technology',
  subtitle: 'Islamabad, Pakistan',
}
const DEFAULT_LOCATION = IST_LOCATION

const FALLBACK_PRESETS = [
  IST_LOCATION,
  { lat: 33.6844, lon: 73.0479, label: 'Islamabad, Pakistan' },
  { lat: 24.8607, lon: 67.0011, label: 'Karachi, Pakistan' },
  { lat: 31.5497, lon: 74.3436, label: 'Lahore, Pakistan' },
  { lat: 34.0151, lon: 71.5249, label: 'Peshawar, Pakistan' },
  { lat: 30.1798, lon: 66.975, label: 'Quetta, Pakistan' },
  { lat: 35.9208, lon: 74.3144, label: 'Gilgit, Pakistan' },
]

const AUTO_REFRESH_MS = 60_000 // satellites move fast — keep "right now" honest

// Roughly the footprint of the IST campus — used only to decide *wording*
// ("IST Campus — Selected Point" vs a plain coordinate) for an arbitrary map
// click. It is not building/block geometry and no such geometry is invented.
const CAMPUS_RADIUS_KM = 1.2
// Clicks this close to the exact IST point are treated as "the" IST marker
// itself, so we don't draw two overlapping pins on first load.
const SAME_POINT_KM = 0.05

function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371
  const toRad = (d) => (d * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

function formatCoord(lat, lon, precision = 5) {
  const latHem = lat >= 0 ? 'N' : 'S'
  const lonHem = lon >= 0 ? 'E' : 'W'
  return `${Math.abs(lat).toFixed(precision)}° ${latHem}  ${Math.abs(lon).toFixed(precision)}° ${lonHem}`
}

// Decides the panel's location title/subtitle for whatever is currently
// selected — a named preset/search result, the IST default, or a bare map
// click — without ever inventing a building/block name.
function describeSelection(point) {
  if (!point) return { title: 'Selected Point', subtitle: 'Worldwide' }
  const distToIST = haversineKm(point.lat, point.lon, IST_LOCATION.lat, IST_LOCATION.lon)

  if (point.label) {
    if (point.label === IST_LOCATION.label) {
      return { title: IST_LOCATION.name, subtitle: IST_LOCATION.subtitle }
    }
    return { title: point.label, subtitle: null }
  }
  if (distToIST <= CAMPUS_RADIUS_KM) {
    return { title: 'IST Campus — Selected Point', subtitle: 'Institute of Space Technology, Islamabad' }
  }
  return { title: 'Selected Point', subtitle: 'Worldwide' }
}

// Distinct pulsing marker for the fixed IST reference point, separate from
// whatever the user has clicked/selected elsewhere.
const istIcon = L.divIcon({
  className: '',
  html: `<div class="ist-marker"><span class="ist-marker-ring"></span><span class="ist-marker-dot"></span></div>`,
  iconSize: [18, 18],
  iconAnchor: [9, 9],
})

const cursorIcon = L.divIcon({
  className: '',
  html: `<div style="width:14px;height:14px;border-radius:50%;background:#C9A227;box-shadow:0 0 0 6px rgba(201,162,39,0.25),0 0 14px #C9A227;"></div>`,
  iconSize: [14, 14],
  iconAnchor: [7, 7],
})

const BASE_LAYERS = {
  street: {
    label: 'Street',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
    attribution:
      'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ, USGS, Intermap, iPC, NRCAN, Esri Japan, METI, Esri China (Hong Kong), Esri (Thailand), TomTom',
  },
  satellite: {
    label: 'Satellite',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution:
      'Tiles &copy; Esri &mdash; Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
  },
}

function ClickCatcher({ onClick }) {
  useMapEvents({
    click(e) {
      onClick(e.latlng.lat, e.latlng.lng, null)
    },
  })
  return null
}

// Recenters/flies the map whenever the selected point changes (preset pick,
// search result, or manual click) without re-mounting the whole map.
function Recenter({ point }) {
  const map = useMap()
  useEffect(() => {
    if (point) map.flyTo([point.lat, point.lon], Math.max(map.getZoom(), 3), { duration: 0.8 })
  }, [point?.lat, point?.lon]) // eslint-disable-line react-hooks/exhaustive-deps
  return null
}

function formatClock(iso) {
  if (!iso) return null
  try {
    const d = new Date(iso)
    return d.toLocaleString(undefined, {
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      day: '2-digit', month: 'short',
    })
  } catch {
    return null
  }
}

export default function VisibilityExplorer() {
  const [presets, setPresets] = useState(FALLBACK_PRESETS)
  const [point, setPoint] = useState(DEFAULT_LOCATION) // {lat, lon, label?}
  const group = 'active'
  const [minElevation, setMinElevation] = useState(10)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [baseLayer, setBaseLayer] = useState('street')
  const refreshRef = useRef(null)

    // Load live presets from the backend (falls back silently to the hardcoded
    // Pakistan-first list above, IST first, if it's not reachable yet).
  useEffect(() => {
    api.locationPresetsGlobal().then((data) => {
      if (data?.presets?.length) setPresets(data.presets)
    }).catch(() => {})
  }, [])

  // Run the default query as soon as the page loads, so the corner panel
  // shows "what's above IST right now" without requiring a click.
  useEffect(() => {
    runQuery(DEFAULT_LOCATION.lat, DEFAULT_LOCATION.lon, group, minElevation, DEFAULT_LOCATION.label)
    return () => clearInterval(refreshRef.current)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Keep "right now" current — satellites move, so silently re-poll.
  useEffect(() => {
    clearInterval(refreshRef.current)
    refreshRef.current = setInterval(() => {
      if (point) runQuery(point.lat, point.lon, group, minElevation, point.label, { silent: true })
    }, AUTO_REFRESH_MS)
    return () => clearInterval(refreshRef.current)
  }, [point, group, minElevation]) // eslint-disable-line react-hooks/exhaustive-deps

  async function runQuery(lat, lon, g = group, minEl = minElevation, label = null, opts = {}) {
    setPoint({ lat, lon, label })
    if (!opts.silent) setLoading(true)
    setError(null)
    try {
      const data = await api.visibleSatellites({ lat, lon, group: g, minElevation: minEl })
      setResult(data)
    } catch (err) {
      // Keep the technical detail (endpoint, status, network error) in the
      // console for development; never surface the raw backend URL to users.
      console.error('[visibility] request failed:', err)
      if (!opts.silent) {
        setResult(null)
        setError('Satellite data temporarily unavailable — unable to connect to the satellite visibility service. Check that the backend service is running.')
      }
    } finally {
      if (!opts.silent) setLoading(false)
    }
  }

  function handleMapClick(lat, lon) {
    runQuery(lat, lon)
  }

  function handleLocationSelect({ lat, lon, label }) {
    runQuery(lat, lon, group, minElevation, label)
  }

  function handleElevationChange(e) {
    const minEl = Number(e.target.value)
    setMinElevation(minEl)
    if (point) runQuery(point.lat, point.lon, group, minEl, point.label)
  }

  const localClock = formatClock(result?.time?.local_iso)
  const tzLabel = result?.time?.timezone
  const { title: locTitle, subtitle: locSubtitle } = describeSelection(point)
  const isSelectionAtIST = point ? haversineKm(point.lat, point.lon, IST_LOCATION.lat, IST_LOCATION.lon) <= SAME_POINT_KM : false

  return (
    <section className="section" id="visibility">
      <div className="section-head">
        <div>
          <h2>Active Satellite Visibility Worldwide</h2>
          <p className="section-subtitle">
            Institute of Space Technology, Islamabad is selected by default — click anywhere on Earth, including the
            IST campus, to see satellites above the horizon at that exact point.
          </p>
        </div>
      </div>

      <div className="vis-layout">
        <div className="vis-map-wrap">
          <div className="vis-map-corner">
            <LocationSearch
              presets={presets}
              currentLabel={point?.label || `${point.lat.toFixed(2)}°, ${point.lon.toFixed(2)}°`}
              onSelect={handleLocationSelect}
              search={api.locationSearchGlobal}
              searchLabel="Search any place worldwide"
              showCoordinates
            />
          </div>
          <div className="vis-layer-toggle" role="group" aria-label="Map style">
            {Object.entries(BASE_LAYERS).map(([key, cfg]) => (
              <button
                key={key}
                type="button"
                className={key === baseLayer ? 'active' : ''}
                onClick={() => setBaseLayer(key)}
              >
                {cfg.label}
              </button>
            ))}
          </div>
          <div className="vis-map">
            <MapContainer center={[point.lat, point.lon]} zoom={4} minZoom={2} worldCopyJump style={{ height: '100%', width: '100%' }}>
              <TileLayer
                key={baseLayer}
                url={BASE_LAYERS[baseLayer].url}
                attribution={BASE_LAYERS[baseLayer].attribution}
              />
              <ClickCatcher onClick={handleMapClick} />
              <Recenter point={point} />

              {/* Fixed reference marker — always shown so the user can find
                  IST while exploring the rest of Pakistan. */}
              <Marker position={[IST_LOCATION.lat, IST_LOCATION.lon]} icon={istIcon}>
                <Popup>
                  <strong>{IST_LOCATION.name}</strong><br />
                  {IST_LOCATION.subtitle}<br />
                  {formatCoord(IST_LOCATION.lat, IST_LOCATION.lon)}
                </Popup>
              </Marker>

              {/* Whatever the user actually selected (click, search, or a
                  non-IST preset) — omitted only when it's effectively the
                  same point as the IST marker above, to avoid a duplicate pin. */}
              {point && !isSelectionAtIST && (
                <Marker position={[point.lat, point.lon]} icon={cursorIcon}>
                  <Popup>
                    Selected Observation Point<br />
                    {formatCoord(point.lat, point.lon)}<br />
                    {result ? `${result.visible_count} satellites visible` : 'Calculating…'}
                  </Popup>
                </Marker>
              )}
            </MapContainer>
          </div>
        </div>

        <div className="vis-panel glass">
          <div className="vis-panel-top">
            <div className="vis-panel-head">
              <span className="vis-eyebrow">Satellite Visibility</span>
              <h3 className="vis-loc-title">{locTitle}</h3>
              {locSubtitle && <p className="vis-loc-subtitle">{locSubtitle}</p>}
              <p className="vis-loc-coords mono">{point ? formatCoord(point.lat, point.lon) : '—'}</p>
            </div>

            <div className="vis-row">
              <div className="vis-field">
                <label>Min elevation°</label>
                <input type="number" min="0" max="90" value={minElevation} onChange={handleElevationChange} />
              </div>
            </div>
          </div>

          <div className="vis-count-block">
            <div className="vis-count-num mono">{loading ? '—' : (result?.visible_count ?? '—')}</div>
            <div className="vis-count-label">Satellites currently visible</div>
          </div>

          {(localClock || tzLabel) && !loading && !error && (
            <p className="loading-hint visibility-time" style={{ color: 'var(--text-faint)' }}>
              As of {localClock}{tzLabel ? ` (${tzLabel})` : ''} · auto-refreshes every 60s
            </p>
          )}

          {loading && <p className="loading-hint">Calculating satellite visibility — propagating orbits with SGP4…</p>}
          {error && <p className="loading-hint" style={{ color: 'var(--amber)' }}>{error}</p>}

          {result && !loading && !error && (
            <div className="vis-list">
              {result.satellites.length === 0 && (
                <p className="empty-hint">Nothing above {minElevation}° elevation in this group right now — try lowering the threshold or a different group.</p>
              )}
              {result.satellites.map((s) => (
                <div className="sat-row" key={s.norad_id}>
                  <span className="name">{s.name}</span>
                  <span className="meta">{s.elevation_deg}° el · {s.azimuth_deg}° az · {s.distance_km.toLocaleString()} km</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
