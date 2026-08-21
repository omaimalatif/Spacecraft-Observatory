import { useEffect, useMemo, useRef, useState } from 'react'
import * as Cesium from 'cesium'
import 'cesium/Build/Cesium/Widgets/widgets.css'
import { api } from '../api.js'

// Same palette already used elsewhere in the Global Assets dashboard, so the
// old fake globe and the real one read as the same product.
const TYPE_COLOR = { PAYLOAD: Cesium.Color.fromCssColorString('#62d6ff'), DEBRIS: Cesium.Color.fromCssColorString('#ffae5e') }
const ORBIT_PATH_COLOR = Cesium.Color.fromCssColorString('#c9a227')

function fmt(n) { return n == null ? 'Data unavailable' : new Intl.NumberFormat().format(n) }

export default function CesiumGlobe({ selected, onSelect }) {
  const containerRef = useRef(null)
  const viewerRef = useRef(null)
  const pointsRef = useRef(null)
  const pathEntityRef = useRef(null)
  const idByPointRef = useRef(new Map())

  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [typeFilter, setTypeFilter] = useState({ PAYLOAD: true, DEBRIS: true })
  const [regimeFilter, setRegimeFilter] = useState({ LEO: true, MEO: true, GEO: true, HEO: true, UNKNOWN: true })
  const [orbitPath, setOrbitPath] = useState(null)
  const [orbitState, setOrbitState] = useState('idle')

  // --- fetch live data once ---
  useEffect(() => {
    api.spaceAssetsGlobeObjects(4000).then(setData).catch((err) => setError(err.message || 'Data unavailable'))
  }, [])

  // --- init the viewer once, offline base imagery so nothing external can take it down ---
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
      terrainProvider: new Cesium.EllipsoidTerrainProvider(), // flat ellipsoid — no terrain service dependency needed for plotting objects
      requestRenderMode: true, // only re-render on change — cheap on CPU with thousands of points
      maximumRequestsPerServer: 6,
    })
    viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString('#050d13')
    viewer.scene.skyAtmosphere.hueShift = -0.05
    viewer.camera.flyHome(0)

    const points = viewer.scene.primitives.add(new Cesium.PointPrimitiveCollection())
    pointsRef.current = points

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

  const visibleObjects = useMemo(() => {
    if (!data?.objects) return []
    return data.objects.filter((o) => typeFilter[o.object_type] && regimeFilter[o.regime ?? 'UNKNOWN'])
  }, [data, typeFilter, regimeFilter])

  const regimeCounts = useMemo(() => {
    const counts = { LEO: 0, MEO: 0, GEO: 0, HEO: 0, UNKNOWN: 0 }
    for (const o of data?.objects ?? []) counts[o.regime ?? 'UNKNOWN'] = (counts[o.regime ?? 'UNKNOWN'] ?? 0) + 1
    return counts
  }, [data])

  // --- (re)draw points whenever the filtered set changes ---
  useEffect(() => {
    const viewer = viewerRef.current
    const points = pointsRef.current
    if (!viewer || !points) return

    points.removeAll()
    idByPointRef.current.clear()
    visibleObjects.forEach((obj, i) => {
      const position = Cesium.Cartesian3.fromDegrees(obj.lon, obj.lat, obj.alt_km * 1000)
      const point = points.add({
        position,
        pixelSize: obj.object_type === 'DEBRIS' ? 3 : 4,
        color: TYPE_COLOR[obj.object_type] ?? Cesium.Color.GRAY,
        outlineColor: Cesium.Color.BLACK.withAlpha(0.4),
        outlineWidth: 0.5,
        id: i,
      })
      idByPointRef.current.set(i, obj)
    })
    viewer.scene.requestRender()
  }, [visibleObjects])

  // --- highlight + fly to the selected object ---
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer || !selected) return
    const target = Cesium.Cartesian3.fromDegrees(selected.lon, selected.lat, selected.alt_km * 1000)
    viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(selected.lon, selected.lat, selected.alt_km * 1000 + 3_000_000),
      duration: 1.0,
    })
    viewer.scene.requestRender()
  }, [selected])

  // --- draw the orbit path polyline when requested ---
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    if (pathEntityRef.current) {
      viewer.entities.remove(pathEntityRef.current)
      pathEntityRef.current = null
    }
    if (orbitPath?.length) {
      const flat = orbitPath.flatMap((p) => [p.lon, p.lat, p.alt_km * 1000])
      pathEntityRef.current = viewer.entities.add({
        polyline: {
          positions: Cesium.Cartesian3.fromDegreesArrayHeights(flat),
          width: 2,
          material: ORBIT_PATH_COLOR.withAlpha(0.85),
          arcType: Cesium.ArcType.NONE,
        },
      })
    }
    viewer.scene.requestRender()
  }, [orbitPath])

  // clear any drawn orbit path when the selection changes
  useEffect(() => { setOrbitPath(null); setOrbitState('idle') }, [selected?.norad_id])

  async function handleShowOrbit() {
    if (!selected) return
    setOrbitState('loading')
    try {
      const result = await api.spaceAssetsOrbitPath(selected.norad_id)
      setOrbitPath(result.path)
      setOrbitState('done')
    } catch {
      setOrbitState('error')
    }
  }

  function toggleType(type) {
    setTypeFilter((f) => ({ ...f, [type]: !f[type] }))
  }

  function toggleRegime(regime) {
    setRegimeFilter((f) => ({ ...f, [regime]: !f[regime] }))
  }

  return (
    <div className="cesium-globe-wrap">
      <div ref={containerRef} className="cesium-canvas" />

      <div className="cesium-overlay cesium-legend">
        <button className={`legend active-dot ${typeFilter.PAYLOAD ? '' : 'off'}`} onClick={() => toggleType('PAYLOAD')}>
          Active payloads {data ? `(${fmt(data.objects.filter((o) => o.object_type === 'PAYLOAD').length)})` : ''}
        </button>
        <button className={`legend debris-dot ${typeFilter.DEBRIS ? '' : 'off'}`} onClick={() => toggleType('DEBRIS')}>
          Debris {data ? `(${fmt(data.objects.filter((o) => o.object_type === 'DEBRIS').length)})` : ''}
        </button>
      </div>

      {data && (
        <div className="cesium-overlay cesium-regime-row">
          {Object.entries(regimeCounts).filter(([, n]) => n > 0).map(([regime, count]) => (
            <button key={regime} className={`legend regime-chip ${regimeFilter[regime] ? '' : 'off'}`} onClick={() => toggleRegime(regime)}>
              {regime} ({fmt(count)})
            </button>
          ))}
        </div>
      )}

      {error && <div className="cesium-overlay cesium-status" style={{ color: '#ffae5e' }}>{error}</div>}
      {!data && !error && <div className="cesium-overlay cesium-status">Fetching live catalog and propagating orbits (SGP4)…</div>}
      {data?.groups_unavailable?.length > 0 && (
        <div className="cesium-overlay cesium-status" style={{ bottom: 12, top: 'auto' }}>
          {data.groups_unavailable.length} of {data.groups_used.length} source groups temporarily unavailable — showing the rest.
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
