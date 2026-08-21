import { useEffect, useRef, useState } from 'react'
import { MapContainer, TileLayer, Marker, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import { api } from '../api.js'
import LocationSearch from './LocationSearch.jsx'

const cursorIcon = L.divIcon({
  className: '',
  html: `<div style="width:14px;height:14px;border-radius:50%;background:#C9A227;box-shadow:0 0 0 6px rgba(201,162,39,0.25),0 0 14px #C9A227;"></div>`,
  iconSize: [14, 14],
  iconAnchor: [7, 7],
})

// Fallback if the backend isn't reachable yet when the page loads — matches
// backend/app/routers/location.py PRESETS[0] so the default view is the same
// either way.
const DEFAULT_LOCATION = { lat: 33.6844, lon: 73.0479, label: 'Islamabad, Pakistan' }
const PAKISTAN_BOUNDS = [[22.5, 59.5], [38.5, 80.5]]
const FALLBACK_PRESETS = [
  DEFAULT_LOCATION,
  { lat: 24.8607, lon: 67.0011, label: 'Karachi, Pakistan' },
  { lat: 31.5497, lon: 74.3436, label: 'Lahore, Pakistan' },
  { lat: 34.0151, lon: 71.5249, label: 'Peshawar, Pakistan' },
  { lat: 30.1798, lon: 66.975, label: 'Quetta, Pakistan' },
  { lat: 35.9208, lon: 74.3144, label: 'Gilgit, Pakistan' },
]

const AUTO_REFRESH_MS = 60_000 // satellites move fast — keep "right now" honest

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
    if (point) map.flyTo([point.lat, point.lon], Math.max(map.getZoom(), 4), { duration: 0.8 })
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
  const refreshRef = useRef(null)

  // Load live presets from the backend (falls back silently to the hardcoded
  // Pakistan-first list above if it's not reachable yet).
  useEffect(() => {
    api.locationPresets().then((data) => {
      if (data?.presets?.length) setPresets(data.presets)
    }).catch(() => {})
  }, [])

  // Run the default query as soon as the page loads, so the corner panel
  // shows "what's above Islamabad right now" without requiring a click.
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
      setError(err.message || 'Could not reach the backend at /api/visibility — is it running?')
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

  return (
    <section className="section" id="visibility">
      <div className="section-head">
        <div>
          <h2>Active Satellite Visibility over Pakistan</h2>
          <p className="section-subtitle">Select a location within Pakistan to view active satellites currently above the horizon.</p>
        </div>
      </div>

      <div className="vis-layout">
        <div className="vis-map-wrap">
          <div className="vis-map-corner">
            <LocationSearch
              presets={presets}
              currentLabel={point?.label || `${point.lat.toFixed(2)}°, ${point.lon.toFixed(2)}°`}
              onSelect={handleLocationSelect}
            />
          </div>
          <div className="vis-map">
            <MapContainer center={[point.lat, point.lon]} zoom={5} minZoom={5} maxBounds={PAKISTAN_BOUNDS} maxBoundsViscosity={1} style={{ height: '100%', width: '100%' }}>
              <TileLayer
                url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
                attribution='&copy; OpenStreetMap contributors &copy; CARTO'
              />
              <ClickCatcher onClick={handleMapClick} />
              <Recenter point={point} />
              {point && <Marker position={[point.lat, point.lon]} icon={cursorIcon} />}
            </MapContainer>
          </div>
        </div>

        <div className="vis-panel glass">
          <div className="vis-row">
            <div className="vis-field" style={{ width: 110 }}>
              <label>Min elevation°</label>
              <input type="number" min="0" max="90" value={minElevation} onChange={handleElevationChange} />
            </div>
          </div>

          {point ? (
            <div className="vis-coords">
              <div className="stat"><b>{point.label || `${point.lat.toFixed(2)}°, ${point.lon.toFixed(2)}°`}</b><span>Location</span></div>
              <div className="stat"><b>{result?.visible_count ?? '—'}</b><span>Visible now</span></div>
            </div>
          ) : (
            <p className="empty-hint">Click anywhere on the map, or search a place above, to see what's overhead.</p>
          )}

          {(localClock || tzLabel) && !loading && !error && (
            <p className="loading-hint" style={{ color: 'var(--text-faint)' }}>
              As of {localClock}{tzLabel ? ` (${tzLabel})` : ''} · auto-refreshes every 60s
            </p>
          )}

          {loading && <p className="loading-hint">Propagating orbits with SGP4…</p>}
          {error && <p className="loading-hint" style={{ color: 'var(--amber)' }}>{error}</p>}

          {result && !loading && (
            <div className="vis-list">
              {result.satellites.length === 0 && (
                <p className="empty-hint">Nothing above {minElevation}° elevation in this group right now — try lowering the threshold or a different group.</p>
              )}
              {result.satellites.map((s) => (
                <div className="sat-row" key={s.norad_id}>
                  <span className="name">{s.name}</span>
                  <span className="meta">{s.elevation_deg}° el · {s.distance_km.toLocaleString()} km</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
