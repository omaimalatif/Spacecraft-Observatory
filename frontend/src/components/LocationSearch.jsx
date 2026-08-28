import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'

// Corner control for the "what's overhead" map: a Pakistan-first preset
// dropdown plus a free-text search box (typing "Multan", "Tokyo", etc. finds
// it via geocoding). Selecting either fires onSelect({ lat, lon, label }).
export default function LocationSearch({ onSelect, presets, currentLabel, search = api.locationSearchGlobal, searchLabel = 'Search any place worldwide', showCoordinates = false }) {
  const [query, setQuery] = useState('')
  const [latitude, setLatitude] = useState('')
  const [longitude, setLongitude] = useState('')
  const [coordinateError, setCoordinateError] = useState(null)
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState(null)
  const debounceRef = useRef(null)

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([])
      setSearchError(null)
      return
    }
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      const normalizedQuery = query.trim().toLowerCase()
      const localMatches = (presets || []).filter((place) => (
        place.label.toLowerCase().includes(normalizedQuery)
      ))
      setResults(localMatches)
      setSearching(true)
      setSearchError(null)
      try {
        const data = await search(query.trim())
        const remoteResults = data.results || []
        const localKeys = new Set(localMatches.map((place) => `${place.lat},${place.lon}`))
        setResults([
          ...localMatches,
          ...remoteResults.filter((place) => !localKeys.has(`${place.lat},${place.lon}`)),
        ])
      } catch (err) {
        setResults(localMatches)
        setSearchError(err.message || 'Search unavailable')
      } finally {
        setSearching(false)
      }
    }, 400)
    return () => clearTimeout(debounceRef.current)
  }, [query, presets, search])

  function pick(place) {
    onSelect({ lat: place.lat, lon: place.lon, label: place.label })
    setQuery('')
    setResults([])
    setOpen(false)
  }

  function pinCoordinates(e) {
    e.preventDefault()
    const lat = Number(latitude)
    const lon = Number(longitude)
    if (!Number.isFinite(lat) || lat < -90 || lat > 90 || !Number.isFinite(lon) || lon < -180 || lon > 180) {
      setCoordinateError('Enter latitude -90 to 90 and longitude -180 to 180.')
      return
    }
    setCoordinateError(null)
    onSelect({ lat, lon, label: `${lat.toFixed(4)}°, ${lon.toFixed(4)}°` })
  }

  return (
    <div className="loc-search">
      <div className="loc-field">
        <label>Quick location</label>
        <select
          className="loc-preset-select"
          value=""
          onChange={(e) => {
            const p = presets.find((x) => x.label === e.target.value)
            if (p) pick(p)
          }}
        >
          <option value="" disabled>{currentLabel || 'Choose a location…'}</option>
          {presets.map((p) => (
            <option key={p.label} value={p.label}>{p.label}</option>
          ))}
        </select>
      </div>

      <div className="loc-field loc-search-field">
        <label>{searchLabel}</label>
        <div className="loc-search-input">
          <input
            type="text"
            placeholder="Search a city, district, region, or landmark…"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setOpen(true) }}
            onFocus={() => setOpen(true)}
            onBlur={() => setTimeout(() => setOpen(false), 150)}
          />
          {open && (searching || results.length > 0 || searchError) && (
            <div className="loc-results glass">
              {searching && <div className="loc-result-hint">Searching…</div>}
              {searchError && <div className="loc-result-hint">{searchError}</div>}
              {!searching && !searchError && results.map((r, i) => (
                <button key={i} className="loc-result" onMouseDown={() => pick(r)}>
                  {r.label}
                </button>
              ))}
              {!searching && !searchError && results.length === 0 && query.trim().length >= 2 && (
                <div className="loc-result-hint">No matches</div>
              )}
            </div>
          )}
        </div>
      </div>

      {showCoordinates && (
        <form className="loc-coordinates" onSubmit={pinCoordinates}>
          <label htmlFor="location-latitude">Pin coordinates</label>
          <div className="loc-coordinate-row">
            <input id="location-latitude" type="number" step="any" min="-90" max="90" placeholder="Latitude" value={latitude} onChange={(e) => setLatitude(e.target.value)} />
            <input id="location-longitude" type="number" step="any" min="-180" max="180" placeholder="Longitude" value={longitude} onChange={(e) => setLongitude(e.target.value)} />
            <button type="submit">Pin</button>
          </div>
          {coordinateError && <span className="loc-coordinate-error">{coordinateError}</span>}
        </form>
      )}
    </div>
  )
}
