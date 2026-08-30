import { useEffect, useMemo, useRef, useState } from 'react'
import * as Cesium from 'cesium'
import 'cesium/Build/Cesium/Widgets/widgets.css'
import { api } from '../api.js'

// One color per altitude band (computed from each CubeSat's own orbital
// elements — see backend/app/routers/cubesat.py — not a name guess, since
// CubeSat missions share no naming convention) so the globe, sky plot
// and legend all agree. Every orbit line, LOS line and point marker is
// colored from this single table — nothing is hardcoded per-render.
export const CATEGORY_COLOR = {
  'Very Low LEO (<400 km)': '#ef4444',
  'Low LEO (400\u2013600 km)': '#eab308',
  'SSO Belt (600\u2013800 km)': '#22c55e',
  'High LEO/Other (800+ km)': '#3b82f6',
  // Defensive fallback only — the backend always tags every object with one
  // of the four bands above, this key is never a real category label.
  Other: '#7d8795',
}

// Earth's true sidereal rotation rate (relative to the stars, not the 24h solar
// day) — used to "de-spin" an Earth-fixed ground-track path back into a
// space-fixed (inertial) one: each path point's longitude gets shifted by how
// far Earth has actually turned between "now" and that point's sample time.
const EARTH_SIDEREAL_DEG_PER_MIN = 360.98564736629 / 1440

// Display order used everywhere the constellations are listed as a legend/row.
export const CATEGORY_ORDER = ['Very Low LEO (<400 km)', 'Low LEO (400\u2013600 km)', 'SSO Belt (600\u2013800 km)', 'High LEO/Other (800+ km)']

const OBSERVER_COLOR = Cesium.Color.fromCssColorString('#e9f8ff')
const GLOBE_POLL_MS = 5 * 60 * 1000 // matches the 5 min backend cache TTL
const ROTATE_RAD_PER_TICK = 0.0009

function fmt(n) { return n == null ? 'Data unavailable' : new Intl.NumberFormat().format(n) }
function cesiumColor(hex) { return Cesium.Color.fromCssColorString(hex) }

export default function CubesatGlobe({ selected, onSelect, presets: presetsProp, location: locationProp, onLocationChange }) {
  const containerRef = useRef(null)
  const wrapRef = useRef(null)
  const viewerRef = useRef(null)
  const pointsRef = useRef(null)
  const labelsRef = useRef(null)
  const orbitEntitiesRef = useRef([])
  const losEntitiesRef = useRef([])
  const observerEntityRef = useRef(null)
  const idByPointRef = useRef(new Map())
  const rotateTimerRef = useRef(null)

  const [data, setData] = useState(null)
  const [status, setStatus] = useState('connecting') // connecting | live | offline
  const [error, setError] = useState(null)
  const [categoryFilter, setConstellationFilter] = useState(
    Object.fromEntries(Object.keys(CATEGORY_COLOR).map((c) => [c, true]))
  )

  const [orbitPathsByNorad, setOrbitPathsByNorad] = useState(null)
  const [orbitState, setOrbitState] = useState('idle')
  const [showOrbits, setShowOrbits] = useState(false)
  // 'earth-fixed' = classic rotating ground track (what was always shown).
  // 'space-fixed' = the same real SGP4 path with Earth's own spin removed,
  // rendered as a stable inertial-frame loop instead.
  const [orbitFrame, setOrbitFrame] = useState('earth-fixed')
  const [showLabels, setShowLabels] = useState(false)
  const [showRotate, setShowRotate] = useState(false)
  const [mask, setMask] = useState(10)
  const [maskInput, setMaskInput] = useState('10')

  // "global" = every cataloged CubeSat on the live catalog, no single location involved.
  // "local"  = only the satellites currently visible above the mask from one chosen
  // location, with a line-of-sight drawn to each. These used to be blended into one
  // overlay (a fixed Islamabad location's LOS lines drawn on top of the full global
  // scatter); they're now a genuine, separate mode so the two readings don't overlap.
  const [viewMode, setViewMode] = useState('global') // 'global' | 'local'

  // Observer location is shared with the availability map/sky-plot further down this
  // portal (lifted into CubesatDashboard) so picking a place there — search, preset,
  // or a map click, anywhere on Earth, not just Pakistan — updates this view too.
  const [fallbackLocation, setFallbackLocation] = useState(null)
  const [fallbackPresets, setFallbackPresets] = useState([])
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

  const [losResult, setLosResult] = useState(null)
  const [losState, setLosState] = useState('idle')

  const [isFullscreen, setIsFullscreen] = useState(false)

  // --- live CubeSat positions, polled on the same cadence as the backend cache ---
  useEffect(() => {
    let cancelled = false
    function poll() {
      api.cubesatGlobeObjects()
        .then((d) => { if (!cancelled) { setData(d); setStatus('live'); setError(null) } })
        .catch((err) => { if (!cancelled) { setStatus('offline'); setError(err.message || 'Data unavailable') } })
    }
    poll()
    const id = setInterval(poll, GLOBE_POLL_MS)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  // --- init the Cesium viewer once ---
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
    return data.objects.filter((o) => categoryFilter[o.category ?? 'Other'])
  }, [data, categoryFilter])

  // In "local" mode, once the visibility result for the chosen location has loaded,
  // narrow the rendered set down to just the satellites above the mask from there —
  // this is what actually separates it from the global scatter instead of drawing
  // LOS lines through all of it.
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

  const categoryCounts = useMemo(() => {
    const counts = {}
    for (const o of data?.objects ?? []) counts[o.category ?? 'Other'] = (counts[o.category ?? 'Other'] ?? 0) + 1
    return counts
  }, [data])

  // --- (re)draw satellite markers + optional labels ---
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
      const color = cesiumColor(CATEGORY_COLOR[obj.category] ?? CATEGORY_COLOR.Other)
      const isSelected = selected?.norad_id === obj.norad_id
      points.add({
        position,
        pixelSize: isSelected ? 8 : 5,
        color,
        outlineColor: isSelected ? Cesium.Color.WHITE : Cesium.Color.BLACK.withAlpha(0.4),
        outlineWidth: isSelected ? 1.5 : 0.5,
        id: i,
      })
      idByPointRef.current.set(i, obj)

      if (showLabels) {
        labels.add({
          position,
          text: obj.name || `NORAD ${obj.norad_id}`,
          font: '11px "JetBrains Mono", monospace',
          fillColor: color,
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
  }, [visibleObjects, showLabels, selected?.norad_id])

  // --- fly to the selected object ---
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer || !selected || !Number.isFinite(selected.lon) || !Number.isFinite(selected.lat) || !Number.isFinite(selected.alt_km)) return
    viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(selected.lon, selected.lat, selected.alt_km * 1000 + 3_000_000),
      duration: 1.0,
    })
    viewer.scene.requestRender()
  }, [selected])

  // --- fetch every satellite's real SGP4-propagated orbit path once "Orbits" is switched on ---
  useEffect(() => {
    if (!showOrbits || orbitPathsByNorad) return
    let cancelled = false
    setOrbitState('loading')
    api.cubesatOrbitPaths()
      .then((result) => {
        if (cancelled) return
        const byNorad = {}
        for (const obj of result.objects || []) byNorad[obj.norad_id] = obj
        setOrbitPathsByNorad(byNorad)
        setOrbitState('done')
      })
      .catch(() => { if (!cancelled) setOrbitState('error') })
    return () => { cancelled = true }
  }, [showOrbits, orbitPathsByNorad])

  // --- draw one real 3D polyline per visible satellite, colored by constellation; ---
  // --- the selected satellite's trajectory is drawn brighter/thicker on top.       ---
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return

    for (const e of orbitEntitiesRef.current) viewer.entities.remove(e)
    orbitEntitiesRef.current = []

    if (showOrbits && orbitPathsByNorad) {
      for (const obj of visibleObjects) {
        const entry = orbitPathsByNorad[obj.norad_id]
        if (!entry?.path?.length) continue
        const isSelected = selected?.norad_id === obj.norad_id
        const color = cesiumColor(CATEGORY_COLOR[obj.category] ?? CATEGORY_COLOR.Other)
        const flat = entry.path.flatMap((p) => {
          let lon = p.lon
          if (orbitFrame === 'space-fixed') {
            // Undo Earth's rotation over this point's offset from "now" so the
            // true orbital loop stays fixed in space instead of sliding with
            // the ground track underneath it.
            lon = ((lon + EARTH_SIDEREAL_DEG_PER_MIN * p.t_min + 180) % 360 + 360) % 360 - 180
          }
          return [lon, p.lat, p.alt_km * 1000]
        })
        const entity = viewer.entities.add({
          polyline: {
            positions: Cesium.Cartesian3.fromDegreesArrayHeights(flat),
            width: isSelected ? 2.5 : 1,
            material: color.withAlpha(isSelected ? 0.95 : 0.35),
            arcType: Cesium.ArcType.NONE,
          },
        })
        orbitEntitiesRef.current.push(entity)
      }
    }
    viewer.scene.requestRender()
  }, [showOrbits, orbitFrame, orbitPathsByNorad, visibleObjects, selected?.norad_id])

  // --- local mode: real elevation-mask-filtered visibility from the chosen observer location ---
  useEffect(() => {
    if (viewMode !== 'local' || !location) { setLosResult(null); setLosState('idle'); return }
    let cancelled = false
    setLosState('loading')
    api.cubesatAvailability({ lat: location.lat, lon: location.lon, minElevation: mask })
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
        point: { pixelSize: 9, color: OBSERVER_COLOR, outlineColor: Cesium.Color.BLACK.withAlpha(0.5), outlineWidth: 1.5 },
        label: {
          text: location.label || `${location.lat.toFixed(2)}°, ${location.lon.toFixed(2)}°`,
          font: '12px "JetBrains Mono", monospace',
          fillColor: OBSERVER_COLOR,
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
        const color = cesiumColor(CATEGORY_COLOR[obj.category] ?? CATEGORY_COLOR.Other)
        const entity = viewer.entities.add({
          polyline: {
            positions: [observerPos, satPos],
            width: 1,
            material: new Cesium.PolylineDashMaterialProperty({ color: color.withAlpha(0.55), dashLength: 12 }),
            arcType: Cesium.ArcType.NONE,
          },
        })
        losEntitiesRef.current.push(entity)
      }
    }
    viewer.scene.requestRender()
  }, [viewMode, location, losResult, data])

  // --- optional slow auto-rotate; user drag/zoom still works normally ---
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    if (rotateTimerRef.current) { clearInterval(rotateTimerRef.current); rotateTimerRef.current = null }
    if (showRotate) {
      rotateTimerRef.current = setInterval(() => {
        viewer.camera.rotateRight(ROTATE_RAD_PER_TICK)
        viewer.scene.requestRender()
      }, 33)
    }
    return () => { if (rotateTimerRef.current) clearInterval(rotateTimerRef.current) }
  }, [showRotate])

  // --- fullscreen toggle on the wrap element, resizing Cesium on change ---
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

  function toggleCategory(c) {
    setConstellationFilter((f) => ({ ...f, [c]: !f[c] }))
  }

  const isLocal = viewMode === 'local'

  return (
    <div ref={wrapRef} className={`cesium-globe-wrap ${isFullscreen ? 'cesium-fullscreen' : ''}`}>
      <div ref={containerRef} className="cesium-canvas" />

      <div className="cesium-overlay cesium-titlebar" style={{ top: 12, left: 12, right: 12 }}>
        <div>
          <p className="cesium-title">3D SATELLITE CATEGORY VIEW</p>
          <p className="cesium-subtitle">
            {isLocal
              ? (location ? `Visible from ${location.label || `${location.lat.toFixed(2)}°, ${location.lon.toFixed(2)}°`}` : 'Pick a location below…')
              : 'All CubeSats, global'}
          </p>
        </div>
      </div>

      {data && (
        <div className="cesium-overlay cesium-controls" style={{ top: 56, left: 12 }}>
          <div className="cesium-chip-row cesium-mode-row">
            <div className="skyplot-mode-toggle cesium-view-mode">
              <button className={!isLocal ? 'active' : ''} onClick={() => setViewMode('global')}>Global</button>
              <button className={isLocal ? 'active' : ''} onClick={() => setViewMode('local')}>Visible from location</button>
            </div>
            {isLocal && (
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
          <div className="cesium-chip-row">
            {[...CATEGORY_ORDER].filter((c) => categoryCounts[c] > 0).map((c) => (
              <button
                key={c}
                className={`legend regime-chip category-chip ${categoryFilter[c] ? '' : 'off'}`}
                style={{ borderColor: CATEGORY_COLOR[c], color: categoryFilter[c] ? CATEGORY_COLOR[c] : undefined }}
                onClick={() => toggleCategory(c)}
              >
                {c} ({fmt(categoryCounts[c])})
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
            <button className={`toggle-pill ${showRotate ? 'active' : ''}`} onClick={() => setShowRotate((v) => !v)}>Rotate</button>
          </div>
        </div>
      )}

      <div className="cesium-overlay cesium-cam-controls" style={{ top: 12, right: 12 }}>
        <button className="skyplot-action skyplot-reset" onClick={resetView}>Reset</button>
        <button className="skyplot-action skyplot-fullscreen-action" onClick={toggleFullscreen}>{isFullscreen ? 'Exit' : 'Fullscreen'}</button>
      </div>

      {error && status === 'offline' && <div className="cesium-overlay cesium-status" style={{ top: 96, color: '#ffae5e' }}>{error}</div>}
      {!data && !error && <div className="cesium-overlay cesium-status" style={{ top: 96 }}>Fetching live CubeSat catalog and propagating orbits (SGP4)…</div>}

      {showOrbits && (
        <div className="cesium-overlay cesium-orbit-btn">
          {orbitState === 'loading' && <small>Propagating orbits for every visible satellite (SGP4)…</small>}
          {orbitState === 'done' && (
            <small style={{ color: '#e68fbf' }}>
              {orbitFrame === 'space-fixed' ? 'Space-fixed (inertial) trajectories' : 'Earth-fixed ground tracks'} shown, one full period each{isLocal ? ' (this location only)' : ''} ✓
            </small>
          )}
          {orbitState === 'error' && <small style={{ color: '#ffae5e' }}>Could not compute orbit paths.</small>}
        </div>
      )}
      {isLocal && (
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
    </div>
  )
}
