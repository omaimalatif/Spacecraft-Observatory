import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'

// Corner control for the "what's overhead" map: a Pakistan-first preset
// dropdown plus a free-text search box (typing "Multan", "Tokyo", etc. finds
// it via geocoding). Selecting either fires onSelect({ lat, lon, label }).
export default function LocationSearch({ onSelect, presets, currentLabel }) {
  const [query, setQuery] = useState('')
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
      setSearching(true)
      setSearchError(null)
      try {
        const data = await api.locationSearch(query.trim())
        setResults(data.results || [])
      } catch (err) {
        setResults([])
        setSearchError(err.message || 'Search unavailable')
      } finally {
        setSearching(false)
      }
    }, 400)
    return () => clearTimeout(debounceRef.current)
  }, [query])

  function pick(place) {
    onSelect({ lat: place.lat, lon: place.lon, label: place.label })
    setQuery('')
    setResults([])
    setOpen(false)
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
        <label>Search any place worldwide</label>
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
    </div>
  )
}
