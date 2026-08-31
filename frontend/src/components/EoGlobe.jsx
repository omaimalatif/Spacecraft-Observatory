import { useEffect, useMemo, useRef, useState } from 'react'
import * as Cesium from 'cesium'
import 'cesium/Build/Cesium/Widgets/widgets.css'
import { api } from '../api.js'
import { CATEGORY_COLOR, CATEGORY_ORDER } from './eoCategories.js'

// Same Cesium setup and CSS classes as Portal 01's globe (CesiumGlobe.jsx) —
// this is the "same 3D visualization" requirement, just recolored by hazard
// focus instead of payload/debris since EO satellites aren't debris.
// Palette itself lives in eoCategories.js (no Cesium dependency) so that
// file can be imported by lighter components without pulling this whole
// module — and therefore Cesium — into their bundle chunk.
const HAZARD_COLOR = Object.fromEntries(Object.entries(CATEGORY_COLOR).map(([k, v]) => [k, Cesium.Color.fromCssColorString(v)]))
const ORBIT_PATH_COLOR = Cesium.Color.fromCssColorString('#c9a227')
const HAZARD_LABELS = CATEGORY_ORDER

function fmt(n) { return n == null ? 'Data unavailable' : new Intl.NumberFormat().format(n) }
function num(n, digits = 0) { return Number.isFinite(Number(n)) ? Number(n).toFixed(digits) : '—' }

export default function EoGlobe({ selected, onSelect, onClose, presets: presetsProp, location: locationProp, onLocationChange }) {
  const containerRef = useRef(null)
  const wrapRef = useRef(null)
  const viewerRef = useRef(null)
  const pointsRef = useRef(null)
  const labelsRef = useRef(null)
  const pathEntityRef = useRef(null)
  const orbitEntitiesRef = useRef([])
  const observerEntityRef = useRef(null)
  const losEntitiesRef = useRef([])
  const idByPointRef = useRef(new Map())

  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [hazardFilter, setHazardFilter] = useState(Object.fromEntries(HAZARD_LABELS.map((l) => [l, true])))
  const [regimeFilter, setRegimeFilter] = useState({ LEO: true, MEO: true, GEO: true, HEO: true, UNKNOWN: true })
  const [orbitPath, setOrbitPath] = useState(null)
  const [orbitPathsByNorad, setOrbitPathsByNorad] = useState(null)
  const [orbitState, setOrbitState] = useState('idle')
  const [showOrbits, setShowOrbits] = useState(false)
  const [showLabels, setShowLabels] = useState(false)
  const [orbitFrame, setOrbitFrame] = useState('earth-fixed')
  const [mask, setMask] = useState(10)
  const [maskInput, setMaskInput] = useState('10')
  const [viewMode, setViewMode] = useState('global')
  const [fallbackLocation, setFallbackLocation] = useState(null)
  const [fallbackPresets, setFallbackPresets] = useState([])
  const [losResult, setLosResult] = useState(null)
  const [losState, setLosState] = useState('idle')
  const [isFullscreen, setIsFullscreen] = useState(false)

  useEffect(() => {
    if (locationProp !== undefined || presetsProp !== undefined) return
    api.locationPresetsGlobal().then((d) => {
      setFallbackPresets(d.presets || [])
      if (d.default) setFallbackLocation(d.default)
    }).catch(() => {})
  }, [locationProp, presetsProp])
  const location = locationProp ?? fallbackLocation
  const setLocation = onLocationChange ?? setFallbackLocation
  const presets = presetsProp ?? fallbackPresets

  useEffect(() => {
    api.earthObservationGlobeObjects().then(setData).catch((err) => setError(err.message || 'Data unavailable'))
  }, [])

  useEffect(() => {
    if (!containerRef.current || viewerRef.current) return

    const viewer = new Cesium.Viewer(containerRef.current, {
      baseLayer: Cesium.ImageryLayer.fromProviderAsync(
        Cesium.TileMapServiceImageryProvider.fromUrl(Cesium.buildModuleUrl('Assets/Textures/NaturalEarthII'))
      ),
      baseLayerPicker: false,
      geocoder: false,
      timeline: false,
      animation: false,
      sceneModePicker: false,
      homeButton: false,
      navigationHelpButton: false,
      fullscreenButton: false,
      infoBox: false,
      selectionIndicator: false,
      terrainProvider: new Cesium.EllipsoidTerrainProvider(),
      requestRenderMode: true,
      maximumRequestsPerServer: 6,
    })
    viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString('#050d13')
    viewer.scene.skyAtmosphere.hueShift = -0.05
    viewer.camera.flyHome(0)

    const points = viewer.scene.primitives.add(new Cesium.PointPrimitiveCollection())
    pointsRef.current = points
    const labels = viewer.scene.primitives.add(new Cesium.LabelCollection())
    labelsRef.current = labels

    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas)
    handler.setInputAction((movement) => {
      const picked = viewer.scene.pick(movement.position)
      if (Cesium.defined(picked) && picked.id != null) {
        const obj = idByPointRef.current.get(picked.id)
        if (obj) onSelect(obj)
      }
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK)

    viewerRef.current = viewer
    return () => {
      handler.destroy()
      viewer.destroy()
      viewerRef.current = null
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const globalVisibleObjects = useMemo(() => {
    if (!data?.objects) return []
    return data.objects.filter((o) => hazardFilter[o.hazard_focus] && regimeFilter[o.regime ?? 'UNKNOWN'])
  }, [data, hazardFilter, regimeFilter])

  const localNoradSet = useMemo(() => {
    if (viewMode !== 'local' || !losResult) return null
    return new Set((losResult.satellites || []).map((s) => s.norad_id))
  }, [viewMode, losResult])

  const visibleObjects = useMemo(() => {
    if (viewMode === 'local' && localNoradSet) {
      return globalVisibleObjects.filter((o) => localNoradSet.has(o.norad_id))
    }
    return globalVisibleObjects
  }, [globalVisibleObjects, viewMode, localNoradSet])

  const regimeCounts = useMemo(() => {
    const counts = { LEO: 0, MEO: 0, GEO: 0, HEO: 0, UNKNOWN: 0 }
    for (const o of data?.objects ?? []) counts[o.regime ?? 'UNKNOWN'] = (counts[o.regime ?? 'UNKNOWN'] ?? 0) + 1
    return counts
  }, [data])

  const hazardCounts = useMemo(() => {
    const counts = Object.fromEntries(HAZARD_LABELS.map((l) => [l, 0]))
    for (const o of data?.objects ?? []) counts[o.hazard_focus] = (counts[o.hazard_focus] ?? 0) + 1
    return counts
  }, [data])

  useEffect(() => {
    const viewer = viewerRef.current
    const points = pointsRef.current
    const labels = labelsRef.current
    if (!viewer || !points || !labels) return

    points.removeAll()
    labels.removeAll()
    idByPointRef.current.clear()
    visibleObjects.forEach((obj, i) => {
      const position = Cesium.Cartesian3.fromDegrees(obj.lon, obj.lat, obj.alt_km * 1000)
      const point = points.add({
        position,
        pixelSize: 4,
        color: HAZARD_COLOR[obj.hazard_focus] ?? Cesium.Color.GRAY,
        outlineColor: Cesium.Color.BLACK.withAlpha(0.4),
        outlineWidth: 0.5,
        id: i,
      })
      idByPointRef.current.set(i, obj)

      if (showLabels) {
        labels.add({
          position,
          text: obj.name || `NORAD ${obj.norad_id}`,
          font: '11px "JetBrains Mono", monospace',
          fillColor: HAZARD_COLOR[obj.hazard_focus] ?? Cesium.Color.WHITE,
          outlineColor: Cesium.Color.BLACK.withAlpha(0.85),
          outlineWidth: 3,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cesium.Cartesian2(9, 0),
          horizontalOrigin: Cesium.HorizontalOrigin.LEFT,
          verticalOrigin: Cesium.VerticalOrigin.CENTER,
          scale: 0.82,
        })
      }
    })
    viewer.scene.requestRender()
}, [visibleObjects, showLabels, showOrbits])

  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer || !selected) return
    if (![selected.lon, selected.lat, selected.alt_km].every(Number.isFinite)) {
      viewer.scene.requestRender()
      return
    }
    viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(selected.lon, selected.lat, selected.alt_km * 1000 + 3_000_000),
      duration: 1.0,
    })
    viewer.scene.requestRender()
  }, [selected])

  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return

    for (const e of orbitEntitiesRef.current) viewer.entities.remove(e)
    orbitEntitiesRef.current = []
    if (pathEntityRef.current) {
      viewer.entities.remove(pathEntityRef.current)
      pathEntityRef.current = null
    }

    if (showOrbits && orbitPathsByNorad) {
      for (const obj of visibleObjects) {
        const entry = orbitPathsByNorad[obj.norad_id]
        if (!entry?.path?.length) continue
        const color = HAZARD_COLOR[obj.hazard_focus] ?? Cesium.Color.WHITE
        const flat = entry.path.flatMap((p) => {
          let lon = p.lon
          if (orbitFrame === 'space-fixed') {
            lon = ((lon + (360.98564736629 / 1440) * p.t_min + 180) % 360 + 360) % 360 - 180
          }
          return [lon, p.lat, p.alt_km * 1000]
        })
        const entity = viewer.entities.add({
          polyline: {
            positions: Cesium.Cartesian3.fromDegreesArrayHeights(flat),
            width: selected?.norad_id === obj.norad_id ? 2.5 : 1,
            material: color.withAlpha(selected?.norad_id === obj.norad_id ? 0.95 : 0.35),
            arcType: Cesium.ArcType.NONE,
          },
        })
        orbitEntitiesRef.current.push(entity)
      }
    }
    viewer.scene.requestRender()
  }, [showOrbits, orbitFrame, orbitPathsByNorad, visibleObjects, selected?.norad_id])

  useEffect(() => { setOrbitPath(null); setOrbitState('idle') }, [selected?.norad_id])

  useEffect(() => {
    if (!showOrbits || !data?.objects) return
    let cancelled = false
    setOrbitState('loading')
    api.earthObservationOrbitPaths()
      .then((result) => {
        if (cancelled) return
        const byNorad = {}
        for (const obj of result?.objects || []) byNorad[obj.norad_id] = obj
        setOrbitPathsByNorad(byNorad)
        const match = result?.objects?.find((o) => o.norad_id === selected?.norad_id)
        if (match) {
          setOrbitPath(match.path || [])
        } else if (result?.objects?.[0]) {
          setOrbitPath(result.objects[0].path || [])
        }
        setOrbitState('done')
      })
      .catch(() => { if (!cancelled) setOrbitState('error') })
    return () => { cancelled = true }
  }, [showOrbits, selected?.norad_id, data])

  useEffect(() => {
    if (viewMode !== 'local' || !location) { setLosResult(null); setLosState('idle'); return }
    let cancelled = false
    setLosState('loading')
    api.earthObservationAvailability({ lat: location.lat, lon: location.lon, minElevation: mask })
      .then((result) => { if (!cancelled) { setLosResult(result); setLosState('done') } })
      .catch(() => { if (!cancelled) setLosState('error') })
    return () => { cancelled = true }
  }, [viewMode, location, mask])

  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    for (const e of losEntitiesRef.current) viewer.entities.remove(e)
    losEntitiesRef.current = []
    if (observerEntityRef.current) { viewer.entities.remove(observerEntityRef.current); observerEntityRef.current = null }

    if (viewMode === 'local' && location && losResult && data?.objects) {
      const byNorad = new Map(data.objects.map((o) => [o.norad_id, o]))
      const observerPos = Cesium.Cartesian3.fromDegrees(location.lon, location.lat, 0)
      observerEntityRef.current = viewer.entities.add({
        position: observerPos,
        point: {
          pixelSize: 9,
          color: Cesium.Color.fromCssColorString('#e9f8ff'),
          outlineColor: Cesium.Color.BLACK.withAlpha(0.5),
          outlineWidth: 1.5,
        },
        label: {
          text: location.label || `${location.lat.toFixed(2)}°, ${location.lon.toFixed(2)}°`,
          font: '12px "JetBrains Mono", monospace',
          fillColor: Cesium.Color.fromCssColorString('#e9f8ff'),
          outlineColor: Cesium.Color.BLACK.withAlpha(0.85),
          outlineWidth: 3,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cesium.Cartesian2(0, -16),
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          scale: 0.9,
        },
      })

      for (const sat of losResult.satellites || []) {
        const obj = byNorad.get(sat.norad_id)
        if (!obj) continue
        const satPos = Cesium.Cartesian3.fromDegrees(obj.lon, obj.lat, obj.alt_km * 1000)
        const entity = viewer.entities.add({
          polyline: {
            positions: [observerPos, satPos],
            width: 1,
            material: new Cesium.PolylineDashMaterialProperty({
              color: HAZARD_COLOR[obj.hazard_focus] ?? Cesium.Color.WHITE,
              dashLength: 12,
            }),
            arcType: Cesium.ArcType.NONE,
          },
        })
        losEntitiesRef.current.push(entity)
      }
    }
    viewer.scene.requestRender()
  }, [viewMode, location, losResult, data])

  useEffect(() => {
    function onChange() {
      const active = document.fullscreenElement === wrapRef.current
      setIsFullscreen(active)
      setTimeout(() => viewerRef.current?.resize(), 60)
    }
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])

  function toggleFullscreen() {
    if (document.fullscreenElement) document.exitFullscreen()
    else wrapRef.current?.requestFullscreen()
  }

  function resetView() {
    viewerRef.current?.camera.flyHome(0.6)
    viewerRef.current?.scene.requestRender()
  }

  function applyMask(value) {
    const v = Math.max(0, Math.min(90, Number(value) || 0))
    setMaskInput(String(v))
    setMask(v)
  }

  async function handleShowOrbit() {
    if (!selected) return
    setShowOrbits(true)
    setOrbitState('loading')
    try {
      const result = await api.earthObservationOrbitPaths()
      const match = result?.objects?.find((o) => o.norad_id === selected.norad_id)
      setOrbitPath(match?.path || [])
      setOrbitState('done')
    } catch {
      setOrbitState('error')
    }
  }

  function toggleHazard(label) {
    setHazardFilter((f) => ({ ...f, [label]: !f[label] }))
  }
  function toggleRegime(regime) {
    setRegimeFilter((f) => ({ ...f, [regime]: !f[regime] }))
  }

  return (
    <div ref={wrapRef} className={`cesium-globe-wrap ${isFullscreen ? 'cesium-fullscreen' : ''}`}>
      <div ref={containerRef} className="cesium-canvas" />

      <div className="cesium-overlay cesium-titlebar" style={{ top: 12, left: 12, right: 12 }}>
        <div>
          <p className="cesium-title">3D EARTH OBSERVATION VIEW</p>
          <p className="cesium-subtitle">
            {viewMode === 'local'
              ? (location ? `Visible from ${location.label || `${location.lat.toFixed(2)}°, ${location.lon.toFixed(2)}°`}` : 'Pick a location below…')
              : 'All EO satellites, global'}
          </p>
        </div>
      </div>

      {data && (
        <div className="cesium-overlay cesium-controls" style={{ top: 56, left: 12 }}>
          <div className="cesium-chip-row cesium-mode-row">
            <div className="skyplot-mode-toggle cesium-view-mode">
              <button className={viewMode === 'global' ? 'active' : ''} onClick={() => setViewMode('global')}>Global</button>
              <button className={viewMode === 'local' ? 'active' : ''} onClick={() => setViewMode('local')}>Visible from location</button>
            </div>
            {viewMode === 'local' && (
              <div className="cesium-location-picker">
                <select
                  className="cesium-location-select"
                  value={location?.label && presets.some((p) => p.label === location.label) ? location.label : ''}
                  onChange={(e) => {
                    const p = presets.find((x) => x.label === e.target.value)
                    if (p) setLocation(p)
                  }}
                >
                  <option value="" disabled>{location?.label || (location ? `${location.lat.toFixed(2)}°, ${location.lon.toFixed(2)}°` : 'Choose a location…')}</option>
                  {presets.map((p) => <option key={p.label} value={p.label}>{p.label}</option>)}
                </select>
                <div className="mask-control">
                  <label>Mask
                    <input
                      type="number" min="0" max="90" value={maskInput}
                      onChange={(e) => setMaskInput(e.target.value)}
                      onBlur={(e) => applyMask(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && applyMask(e.target.value)}
                    />°
                  </label>
                </div>
              </div>
            )}
          </div>

          <div className="cesium-overlay cesium-legend eo-hazard-legend" style={{ position: 'static', display: 'flex' }}>
            {HAZARD_LABELS.map((label) => (
              <button
                key={label}
                className={`legend eo-hazard-dot ${hazardFilter[label] ? '' : 'off'}`}
                style={{ '--dot': HAZARD_COLOR[label]?.toCssColorString() }}
                onClick={() => toggleHazard(label)}
              >
                {label} {data ? `(${fmt(hazardCounts[label])})` : ''}
              </button>
            ))}
          </div>

          <div className="cesium-chip-row cesium-regime-row">
            {Object.entries(regimeCounts).filter(([, n]) => n > 0).map(([regime, count]) => (
              <button key={regime} className={`legend regime-chip regime-${regime.toLowerCase()} ${regimeFilter[regime] ? '' : 'off'}`} onClick={() => toggleRegime(regime)}>
                {regime} ({fmt(count)})
              </button>
            ))}
          </div>

          <div className="cesium-chip-row cesium-toggle-row">
            <button className={`toggle-pill ${showOrbits ? 'active' : ''}`} onClick={() => setShowOrbits((v) => !v)}>Orbits</button>
            {showOrbits && (
              <div className="skyplot-mode-toggle cesium-orbit-frame">
                <button className={orbitFrame === 'earth-fixed' ? 'active' : ''} onClick={() => setOrbitFrame('earth-fixed')} title="Ground track — rotates with Earth beneath the orbit">Earth-fixed</button>
                <button className={orbitFrame === 'space-fixed' ? 'active' : ''} onClick={() => setOrbitFrame('space-fixed')} title="Inertial path — Earth's own spin removed">Space-fixed</button>
              </div>
            )}
            <button className={`toggle-pill ${showLabels ? 'active' : ''}`} onClick={() => setShowLabels((v) => !v)}>Labels</button>
          </div>
        </div>
      )}

      <div className="cesium-overlay cesium-cam-controls" style={{ top: 12, right: 12 }}>
        <button className="skyplot-action skyplot-reset" onClick={resetView}>Reset</button>
        <button className="skyplot-action skyplot-fullscreen-action" onClick={toggleFullscreen}>{isFullscreen ? 'Exit' : 'Fullscreen'}</button>
      </div>

      {error && <div className="cesium-overlay cesium-status" style={{ color: '#ffae5e', top: 96 }}>{error}</div>}
      {!data && !error && <div className="cesium-overlay cesium-status" style={{ top: 96 }}>Fetching live EO catalog and propagating orbits (SGP4)…</div>}
      {data?.groups_unavailable?.length > 0 && (
        <div className="cesium-overlay cesium-status" style={{ bottom: 12, top: 'auto' }}>
          {data.groups_unavailable.length} of {data.groups_used.length} source groups temporarily unavailable — showing the rest.
        </div>
      )}

      {showOrbits && (
        <div className="cesium-overlay cesium-orbit-btn">
          {orbitState === 'loading' && <small>Propagating orbit paths for Earth-observation satellites…</small>}
          {orbitState === 'done' && (
            <small style={{ color: '#e68fbf' }}>
              {orbitFrame === 'space-fixed' ? 'Space-fixed (inertial) trajectories' : 'Earth-fixed ground tracks'} shown, one full period each{viewMode === 'local' ? ' (this location only)' : ''} ✓
            </small>
          )}
          {orbitState === 'error' && <small style={{ color: '#ffae5e' }}>Could not compute orbit paths.</small>}
        </div>
      )}

      {viewMode === 'local' && losState !== 'idle' && (
        <div className="cesium-overlay cesium-los-btn">
          {losState === 'loading' && <small>Computing real elevation angles from observer…</small>}
          {losState === 'done' && (
            <small style={{ color: '#e9f8ff' }}>
              {fmt(losResult?.visible_count)} of {fmt(data?.objects?.length)} satellites above {mask}° from {location ? (location.label || `${location.lat.toFixed(2)}°, ${location.lon.toFixed(2)}°`) : 'observer'} ✓
            </small>
          )}
          {losState === 'error' && <small style={{ color: '#ffae5e' }}>Could not compute line-of-sight.</small>}
        </div>
      )}

      {selected && (
        <div className="cesium-overlay cesium-profile">
          <button className="close" onClick={onClose}>×</button>
          <span className="eyebrow">LIVE OBJECT PROFILE</span>
          <h3>{selected.name}</h3>
          <p className="object-id">NORAD {selected.norad_id} · {selected.cospar_id || 'COSPAR unavailable'}</p>
          <div className="profile-grid">
            <label>Object type<b>Satellite</b></label>
            <label>Status<b className={selected.ops_status === 'active' ? 'is-active' : selected.ops_status === 'inactive' ? 'is-inactive' : ''}>
              {selected.ops_status === 'active' ? 'Active' : selected.ops_status === 'inactive' ? 'Inactive' : 'Unknown'}
            </b></label>
            <label>Hazard focus<b>{selected.hazard_focus}</b></label>
            <label>Orbital regime<b>{selected.regime}</b></label>
            <label>Latitude<b>{num(selected.lat, 2)}°</b></label>
            <label>Longitude<b>{num(selected.lon, 2)}°</b></label>
            <label>Epoch<b>{selected.epoch ? new Date(selected.epoch).toLocaleDateString() : '—'}</b></label>
            <label>Altitude (current)<b>{selected.alt_km == null ? '—' : `${fmt(selected.alt_km)} km`}</b></label>
            <label>Inclination<b>{selected.inclination_deg != null ? `${num(selected.inclination_deg, 2)}°` : '—'}</b></label>
            <label>Period<b>{selected.period_min != null ? `${num(selected.period_min, 1)} min` : '—'}</b></label>
            <label>Eccentricity<b>{num(selected.eccentricity, 5)}</b></label>
            <label>Mean motion<b>{selected.mean_motion_rev_day != null ? `${num(selected.mean_motion_rev_day, 6)} rev/day` : '—'}</b></label>
            <label>Mean anomaly<b>{selected.mean_anomaly_deg != null ? `${num(selected.mean_anomaly_deg, 2)}°` : '—'}</b></label>
            <label>Argument of perigee<b>{selected.argument_of_perigee_deg != null ? `${num(selected.argument_of_perigee_deg, 2)}°` : '—'}</b></label>
            <label>RAAN<b>{selected.raan_deg != null ? `${num(selected.raan_deg, 2)}°` : '—'}</b></label>
            <label>Semi-major axis<b>{selected.semi_major_axis_km != null ? `${fmt(selected.semi_major_axis_km)} km` : '—'}</b></label>
            <label>Perigee altitude<b>{selected.perigee_alt_km != null ? `${fmt(selected.perigee_alt_km)} km` : '—'}</b></label>
            <label>Apogee altitude<b>{selected.apogee_alt_km != null ? `${fmt(selected.apogee_alt_km)} km` : '—'}</b></label>
          </div>
        </div>
      )}

      {selected && (
        <div className="cesium-overlay cesium-orbit-btn">
          <button className="legend" onClick={handleShowOrbit} disabled={orbitState === 'loading'}>
            {orbitState === 'loading' ? 'Propagating orbit…' : orbitPath ? 'Orbit shown ✓' : 'View its orbit'}
          </button>
          {orbitState === 'error' && <small style={{ color: '#ffae5e' }}>Could not compute orbit path.</small>}
        </div>
      )}
    </div>
  )
}