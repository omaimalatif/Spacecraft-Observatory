import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, Marker, CircleMarker, Popup, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import { CATEGORY_COLOR, CATEGORY_ORDER } from './CubesatGlobe.jsx'

const markerIcon = L.divIcon({
  className: '',
  html: `<div style="width:14px;height:14px;border-radius:50%;background:#e68fbf;box-shadow:0 0 0 6px rgba(230,143,191,0.25),0 0 14px #e68fbf;"></div>`,
  iconSize: [14, 14],
  iconAnchor: [7, 7],
})

function ClickCatcher({ onClick }) {
  useMapEvents({
    click(e) { onClick(e.latlng.lat, e.latlng.lng) },
  })
  return null
}

function Recenter({ lat, lon }) {
  const map = useMap()
  useEffect(() => {
    if (lat != null && lon != null) map.flyTo([lat, lon], Math.max(map.getZoom(), 3), { duration: 0.6 })
  }, [lat, lon]) // eslint-disable-line react-hooks/exhaustive-deps
  return null
}

function ResizeMap({ fullscreen }) {
  const map = useMap()
  useEffect(() => {
    const timer = setTimeout(() => map.invalidateSize(), 120)
    return () => clearTimeout(timer)
  }, [fullscreen, map])
  return null
}

// Click anywhere on Earth to pick an observer location without a
// country/region restriction.
export default function CubesatLocationPicker({ lat, lon, onPick, satellites = [] }) {
  const [fullscreen, setFullscreen] = useState(false)

  return (
    <div className={`world-picker-map ${fullscreen ? 'world-picker-map-fullscreen' : ''}`}>
      <button
        type="button"
        className="map-fullscreen-button"
        onClick={() => setFullscreen((value) => !value)}
        aria-label={fullscreen ? 'Exit fullscreen map' : 'Open fullscreen map'}
      >
        {fullscreen ? 'Exit' : 'Fullscreen'}
      </button>
      <div className="map-category-legend" aria-label="Satellite category legend">
        <strong>Satellite categories</strong>
        {CATEGORY_ORDER.map((category) => (
          <span key={category}>
            <i style={{ background: CATEGORY_COLOR[category] }} />{category}
          </span>
        ))}
        <span><i className="location-key" />Selected location</span>
      </div>
      <MapContainer
        center={[lat ?? 20, lon ?? 0]}
        zoom={lat != null ? 4 : 2}
        minZoom={2}
        worldCopyJump
        style={{ height: '100%', width: '100%' }}
      >
        <ResizeMap fullscreen={fullscreen} />
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}"
          attribution="Tiles &copy; Esri"
        />
        <ClickCatcher onClick={(clickLat, clickLon) => onPick({ lat: clickLat, lon: clickLon, label: null })} />
        <Recenter lat={lat} lon={lon} />
        {lat != null && lon != null && <Marker position={[lat, lon]} icon={markerIcon} />}
        {satellites.map((satellite) => (
          <CircleMarker
            key={satellite.norad_id}
            center={[satellite.lat, satellite.lon]}
            radius={5}
            pathOptions={{
              color: CATEGORY_COLOR[satellite.category] || CATEGORY_COLOR.Other,
              fillColor: CATEGORY_COLOR[satellite.category] || CATEGORY_COLOR.Other,
              fillOpacity: 0.85,
              weight: 1,
            }}
          >
            <Tooltip direction="top" offset={[0, -5]}>
              <strong>{satellite.name || `NORAD ${satellite.norad_id}`}</strong>
              <br />{satellite.category || 'Unknown category'}
            </Tooltip>
            <Popup>{satellite.name || `NORAD ${satellite.norad_id}`}<br />{satellite.alt_km?.toLocaleString()} km altitude</Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  )
}