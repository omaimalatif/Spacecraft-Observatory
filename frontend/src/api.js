const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

async function get(path) {
  let res
  try {
    res = await fetch(`${API_BASE}${path}`)
  } catch (err) {
    // fetch itself throws on network failure (backend not running, wrong
    // port, actual CORS block) — distinguish that from a backend error reply
    throw new Error(`Could not reach the backend at ${API_BASE}${path} — is it running? (${err.message})`)
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch { /* body wasn't JSON — keep statusText */ }
    throw new Error(`API ${path} failed: ${res.status} ${detail}`)
  }
  return res.json()
}

export const api = {
  health: () => get('/api/health'),
  spaceAssetsSummary: () => get('/api/space-assets/summary'),
  spaceAssetsDashboard: () => get('/api/space-assets/dashboard'),
  spaceAssetsGlobeObjects: (maxTotal = 22000) => get(`/api/space-assets/globe-objects?max_total=${maxTotal}`),
  spaceAssetsOrbitPath: (noradId) => get(`/api/space-assets/orbit-path/${noradId}`),
  spaceAssetsObjects: (group = 'active') => get(`/api/space-assets/objects?group=${encodeURIComponent(group)}`),
  spaceAssetsByCountry: () => get('/api/space-assets/by-country'),
  spaceAssetsByCountryDetail: (ownerCode) => get(`/api/space-assets/by-country/${encodeURIComponent(ownerCode)}`),
  spaceAssetsComposition: () => get('/api/space-assets/orbital-snapshot/composition'),
  spaceAssetsTypes: () => get('/api/space-assets/orbital-snapshot/types'),
  spaceAssetsRegimeFull: (objectType = 'payload') => get(`/api/space-assets/orbital-snapshot/regime-full?object_type=${objectType}`),
  spaceAssetsAltitude: (objectType = 'all') => get(`/api/space-assets/orbital-snapshot/altitude?object_type=${objectType}`),
  searchSpaceAssets: (query) => get(`/api/space-assets/search?q=${encodeURIComponent(query)}`),
  visibilityGroups: () => get('/api/visibility/groups'),
  visibleSatellites: ({ lat, lon, group = 'stations', minElevation = 10 }) =>
    get(`/api/visibility?lat=${lat}&lon=${lon}&group=${group}&min_elevation_deg=${minElevation}`),
  locationPresetsGlobal: () => get('/api/location/presets-global'),
  locationSearchGlobal: (q) => get(`/api/location/search-global?q=${encodeURIComponent(q)}`),
  issNow: () => get('/api/human-spaceflight/iss-now'),
  peopleInSpace: () => get('/api/human-spaceflight/people-in-space'),
  navigationConstellations: () => get('/api/navigation/constellations'),
  navigationOverview: () => get('/api/navigation/overview'),
  navigationSatellites: ({ constellation, q, limit = 500 } = {}) => {
    const params = new URLSearchParams()
    if (constellation) params.set('constellation', constellation)
    if (q) params.set('q', q)
    if (limit) params.set('limit', limit)
    return get(`/api/navigation/satellites?${params.toString()}`)
  },
  navigationGlobeObjects: () => get('/api/navigation/globe-objects'),
  navigationOrbitPath: (noradId) => get(`/api/navigation/orbit-path/${noradId}`),
  navigationOrbitPaths: () => get('/api/navigation/orbit-paths'),
  navigationAvailability: ({ lat, lon, minElevation = 10 }) =>
    get(`/api/navigation/availability?lat=${lat}&lon=${lon}&min_elevation_deg=${minElevation}`),
  navigationServiceInfo: () => get('/api/navigation/service-info'),
  navigationSkyTrack: (noradId, { lat, lon, windowMin = 60 }) =>
    get(`/api/navigation/sky-track/${noradId}?lat=${lat}&lon=${lon}&window_min=${windowMin}`),
  navigationSkyTracks: ({ lat, lon, minElevation = 10, windowMin = 25 }) =>
    get(`/api/navigation/sky-tracks?lat=${lat}&lon=${lon}&min_elevation_deg=${minElevation}&window_min=${windowMin}`),
  earthObservationEvents: () => get('/api/earth-observation/events'),
  earthObservationLayers: () => get('/api/earth-observation/layers'),
  earthObservationFires: (bbox = 'world') => get(`/api/earth-observation/fires?bbox=${encodeURIComponent(bbox)}`),
  earthObservationSatellites: () => get('/api/earth-observation/satellites'),
  earthObservationStatus: () => get('/api/earth-observation/status'),
  spaceScienceSolarSystem: () => get('/api/space-science/solar-system'),
  spaceScienceSpacecraft: () => get('/api/space-science/spacecraft'),
  spaceScienceNeo: (days = 7) => get(`/api/space-science/neo?days=${days}`),
  spaceScienceStatus: () => get('/api/space-science/status'),
}
