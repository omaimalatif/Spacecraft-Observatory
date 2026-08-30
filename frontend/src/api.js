const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'
const REQUEST_TIMEOUT_MS = 25000 // a stalled backend/upstream call fails cleanly instead of hanging the UI forever

async function fetchWithTimeout(url) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  try {
    return await fetch(url, { signal: controller.signal })
  } finally {
    clearTimeout(timer)
  }
}

async function get(path, { retry = true } = {}) {
  let res
  try {
    res = await fetchWithTimeout(`${API_BASE}${path}`)
  } catch (err) {
    // Network failure or timeout — retry once (covers a transient blip)
    // before surfacing an error, since a single dropped request shouldn't
    // make an otherwise-working backend look "blocked".
    if (retry) return get(path, { retry: false })
    const reason = err.name === 'AbortError' ? `timed out after ${REQUEST_TIMEOUT_MS / 1000}s` : err.message
    throw new Error(`Could not reach the backend at ${API_BASE}${path} — is it running? (${reason})`)
  }
  if (!res.ok) {
    // 502/503/504 are frequently transient (upstream rate-limited a single
    // request) — one retry avoids surfacing a failure the very next request
    // would have avoided.
    if (retry && [502, 503, 504].includes(res.status)) return get(path, { retry: false })
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
  earthObservationGlobeObjects: () => get('/api/earth-observation/globe-objects'),
  earthObservationTypes: () => get('/api/earth-observation/types'),
  spaceScienceSolarSystem: () => get('/api/space-science/solar-system'),
  spaceScienceSpacecraft: () => get('/api/space-science/spacecraft'),
  spaceScienceNeo: (days = 7) => get(`/api/space-science/neo?days=${days}`),
  spaceScienceStatus: () => get('/api/space-science/status'),

  // Portal 04 — Communication satellites (CelesTrak Intelsat/SES/Eutelsat/Telesat/
  // Iridium NEXT/Orbcomm/Globalstar/Amateur groups)
  communicationOverview: () => get('/api/communication/overview'),
  communicationCategories: () => get('/api/communication/categories'),
  communicationSatellites: ({ category, q, limit = 500 } = {}) => {
    const params = new URLSearchParams()
    if (category) params.set('category', category)
    if (q) params.set('q', q)
    if (limit) params.set('limit', limit)
    return get(`/api/communication/satellites?${params.toString()}`)
  },
  communicationGlobeObjects: () => get('/api/communication/globe-objects'),
  communicationOrbitPath: (noradId) => get(`/api/communication/orbit-path/${noradId}`),
  communicationOrbitPaths: () => get('/api/communication/orbit-paths'),
  communicationAvailability: ({ lat, lon, minElevation = 10 }) =>
    get(`/api/communication/availability?lat=${lat}&lon=${lon}&min_elevation_deg=${minElevation}`),
  communicationServiceInfo: () => get('/api/communication/service-info'),
  communicationSkyTrack: (noradId, { lat, lon, windowMin = 60 }) =>
    get(`/api/communication/sky-track/${noradId}?lat=${lat}&lon=${lon}&window_min=${windowMin}`),
  communicationSkyTracks: ({ lat, lon, minElevation = 10, windowMin = 25 }) =>
    get(`/api/communication/sky-tracks?lat=${lat}&lon=${lon}&min_elevation_deg=${minElevation}&window_min=${windowMin}`),

  // Portal 05 — Meteorological & Environmental satellites (CelesTrak GROUP=weather)
  meteorologicalOverview: () => get('/api/meteorological/overview'),
  meteorologicalCategories: () => get('/api/meteorological/categories'),
  meteorologicalSatellites: ({ category, q, limit = 500 } = {}) => {
    const params = new URLSearchParams()
    if (category) params.set('category', category)
    if (q) params.set('q', q)
    if (limit) params.set('limit', limit)
    return get(`/api/meteorological/satellites?${params.toString()}`)
  },
  meteorologicalGlobeObjects: () => get('/api/meteorological/globe-objects'),
  meteorologicalOrbitPath: (noradId) => get(`/api/meteorological/orbit-path/${noradId}`),
  meteorologicalOrbitPaths: () => get('/api/meteorological/orbit-paths'),
  meteorologicalAvailability: ({ lat, lon, minElevation = 10 }) =>
    get(`/api/meteorological/availability?lat=${lat}&lon=${lon}&min_elevation_deg=${minElevation}`),
  meteorologicalServiceInfo: () => get('/api/meteorological/service-info'),
  meteorologicalSkyTrack: (noradId, { lat, lon, windowMin = 60 }) =>
    get(`/api/meteorological/sky-track/${noradId}?lat=${lat}&lon=${lon}&window_min=${windowMin}`),
  meteorologicalSkyTracks: ({ lat, lon, minElevation = 10, windowMin = 25 }) =>
    get(`/api/meteorological/sky-tracks?lat=${lat}&lon=${lon}&min_elevation_deg=${minElevation}&window_min=${windowMin}`),

  // Portal 07 add-on — Human Spaceflight satellites (CelesTrak GROUP=stations)
  humanSpaceflightSatOverview: () => get('/api/human-spaceflight-sat/overview'),
  humanSpaceflightSatCategories: () => get('/api/human-spaceflight-sat/categories'),
  humanSpaceflightSatSatellites: ({ category, q, limit = 500 } = {}) => {
    const params = new URLSearchParams()
    if (category) params.set('category', category)
    if (q) params.set('q', q)
    if (limit) params.set('limit', limit)
    return get(`/api/human-spaceflight-sat/satellites?${params.toString()}`)
  },
  humanSpaceflightSatGlobeObjects: () => get('/api/human-spaceflight-sat/globe-objects'),
  humanSpaceflightSatOrbitPath: (noradId) => get(`/api/human-spaceflight-sat/orbit-path/${noradId}`),
  humanSpaceflightSatOrbitPaths: () => get('/api/human-spaceflight-sat/orbit-paths'),
  humanSpaceflightSatAvailability: ({ lat, lon, minElevation = 10 }) =>
    get(`/api/human-spaceflight-sat/availability?lat=${lat}&lon=${lon}&min_elevation_deg=${minElevation}`),
  humanSpaceflightSatServiceInfo: () => get('/api/human-spaceflight-sat/service-info'),
  humanSpaceflightSatSkyTrack: (noradId, { lat, lon, windowMin = 60 }) =>
    get(`/api/human-spaceflight-sat/sky-track/${noradId}?lat=${lat}&lon=${lon}&window_min=${windowMin}`),
  humanSpaceflightSatSkyTracks: ({ lat, lon, minElevation = 10, windowMin = 25 }) =>
    get(`/api/human-spaceflight-sat/sky-tracks?lat=${lat}&lon=${lon}&min_elevation_deg=${minElevation}&window_min=${windowMin}`),

  // Portal 08 — CubeSat & Small Satellites (CelesTrak GROUP=cubesat)
  cubesatOverview: () => get('/api/cubesat/overview'),
  cubesatCategories: () => get('/api/cubesat/categories'),
  cubesatSatellites: ({ category, q, limit = 500 } = {}) => {
    const params = new URLSearchParams()
    if (category) params.set('category', category)
    if (q) params.set('q', q)
    if (limit) params.set('limit', limit)
    return get(`/api/cubesat/satellites?${params.toString()}`)
  },
  cubesatGlobeObjects: () => get('/api/cubesat/globe-objects'),
  cubesatOrbitPath: (noradId) => get(`/api/cubesat/orbit-path/${noradId}`),
  cubesatOrbitPaths: () => get('/api/cubesat/orbit-paths'),
  cubesatAvailability: ({ lat, lon, minElevation = 10 }) =>
    get(`/api/cubesat/availability?lat=${lat}&lon=${lon}&min_elevation_deg=${minElevation}`),
  cubesatServiceInfo: () => get('/api/cubesat/service-info'),
  cubesatSkyTrack: (noradId, { lat, lon, windowMin = 60 }) =>
    get(`/api/cubesat/sky-track/${noradId}?lat=${lat}&lon=${lon}&window_min=${windowMin}`),
  cubesatSkyTracks: ({ lat, lon, minElevation = 10, windowMin = 25 }) =>
    get(`/api/cubesat/sky-tracks?lat=${lat}&lon=${lon}&min_elevation_deg=${minElevation}&window_min=${windowMin}`),

  // Portal 06 add-on — Space Science satellites (CelesTrak GROUP=science)
  spaceScienceSatOverview: () => get('/api/space-science-sat/overview'),
  spaceScienceSatCategories: () => get('/api/space-science-sat/categories'),
  spaceScienceSatSatellites: ({ category, q, limit = 500 } = {}) => {
    const params = new URLSearchParams()
    if (category) params.set('category', category)
    if (q) params.set('q', q)
    if (limit) params.set('limit', limit)
    return get(`/api/space-science-sat/satellites?${params.toString()}`)
  },
  spaceScienceSatGlobeObjects: () => get('/api/space-science-sat/globe-objects'),
  spaceScienceSatOrbitPath: (noradId) => get(`/api/space-science-sat/orbit-path/${noradId}`),
  spaceScienceSatOrbitPaths: () => get('/api/space-science-sat/orbit-paths'),
  spaceScienceSatAvailability: ({ lat, lon, minElevation = 10 }) =>
    get(`/api/space-science-sat/availability?lat=${lat}&lon=${lon}&min_elevation_deg=${minElevation}`),
  spaceScienceSatServiceInfo: () => get('/api/space-science-sat/service-info'),
  spaceScienceSatSkyTrack: (noradId, { lat, lon, windowMin = 60 }) =>
    get(`/api/space-science-sat/sky-track/${noradId}?lat=${lat}&lon=${lon}&window_min=${windowMin}`),
  spaceScienceSatSkyTracks: ({ lat, lon, minElevation = 10, windowMin = 25 }) =>
    get(`/api/space-science-sat/sky-tracks?lat=${lat}&lon=${lon}&min_elevation_deg=${minElevation}&window_min=${windowMin}`),
}