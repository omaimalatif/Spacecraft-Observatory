import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { api } from '../api.js'
import { CATEGORY_COLOR, CATEGORY_ORDER } from './SciGlobe.jsx'

const MASK_PRESETS = [0, 5, 10, 15, 20]
const SIZE = 480
const C = SIZE / 2
const R = SIZE / 2 - 42 // leave room for cardinal labels

function shortLabel(name) {
  const m = /\(([^)]+)\)\s*$/.exec(name || '')
  const inner = m ? m[1] : (name || '').trim()
  const prn = /PRN\s*0*(\d+)/i.exec(inner)
  if (prn) return prn[1]
  return inner.replace(/\s+/g, '').slice(0, 6)
}

// --- 2D projection: standard polar sky plot, zenith at center ---------------
function project2D(azimuthDeg, elevationDeg) {
  const az = (azimuthDeg * Math.PI) / 180
  const r = ((90 - elevationDeg) / 90) * R
  return { x: C + r * Math.sin(az), y: C - r * Math.cos(az), scale: 1 }
}

// --- 3D projection: tilted-dome pseudo-3D, no WebGL dependency needed ------
// Real azimuth/elevation converted to a 3D unit vector (x = east-west,
// yDepth = north-south, zHeight = up), then projected with a fixed camera
// tilt so higher elevation reads as "higher on screen" and satellites to
// the north recede while southern ones sit forward/larger — an honest
// geometric projection of the same real numbers, not a different dataset.
const TILT = 0.62
function project3D(azimuthDeg, elevationDeg) {
  const az = (azimuthDeg * Math.PI) / 180
  const el = (elevationDeg * Math.PI) / 180
  const x = Math.cos(el) * Math.sin(az)
  const yDepth = Math.cos(el) * Math.cos(az)
  const zHeight = Math.sin(el)
  const scale = 0.6 + 0.4 * ((1 - yDepth) / 2) // satellites toward viewer (south) render slightly larger
  return {
    x: C + x * R,
    y: C - zHeight * R * 0.92 - yDepth * R * TILT * 0.5,
    scale,
  }
}

function ringPath2D(elevationDeg) {
  const r = ((90 - elevationDeg) / 90) * R
  return { cx: C, cy: C, r }
}
function ringEllipse3D(elevationDeg) {
  // horizon ring (el=0) is the tilted floor ellipse; higher rings are
  // smaller ellipses lifted up, same dome logic as project3D's z/y terms.
  const el = (elevationDeg * Math.PI) / 180
  const zHeight = Math.sin(el)
  const rx = R * Math.cos(el)
  const ry = rx * TILT * 0.5
  return { cx: C, cy: C - zHeight * R * 0.92, rx, ry: Math.max(ry, 0.001) }
}

function Globe3D({ satellites, tracks, onSelect, showLabels, showLOS, showOrbits }) {
  const mountRef = useRef(null)
  const sceneRef = useRef(null)

  useEffect(() => {
    const mount = mountRef.current
    if (!mount || sceneRef.current) return undefined
    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100)
    camera.position.set(0, 1.2, 3.2)
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    mount.appendChild(renderer.domElement)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.07
    controls.minDistance = 1.7
    controls.maxDistance = 7

    scene.add(new THREE.AmbientLight(0x8bb8d8, 1.5))
    const light = new THREE.DirectionalLight(0xffffff, 2.2)
    light.position.set(3, 4, 5)
    scene.add(light)

    const earth = new THREE.Mesh(
      new THREE.SphereGeometry(1, 64, 64),
      new THREE.MeshStandardMaterial({ color: 0x176080, roughness: 0.76, metalness: 0.04 })
    )
    scene.add(earth)
    const grid = new THREE.Mesh(
      new THREE.SphereGeometry(1.006, 32, 20),
      new THREE.MeshBasicMaterial({ color: 0x7ddff5, wireframe: true, transparent: true, opacity: 0.16 })
    )
    scene.add(grid)
    const atmosphere = new THREE.Mesh(
      new THREE.SphereGeometry(1.045, 64, 64),
      new THREE.MeshBasicMaterial({ color: 0x52cfff, transparent: true, opacity: 0.11, side: THREE.BackSide })
    )
    scene.add(atmosphere)

    const stars = new THREE.Points(
      new THREE.SphereGeometry(8, 24, 24),
      new THREE.PointsMaterial({ color: 0xaadfff, size: 0.025, sizeAttenuation: true })
    )
    scene.add(stars)

    const points = new THREE.Group()
    scene.add(points)
    const pointData = new Map()
    const raycaster = new THREE.Raycaster()
    const pointer = new THREE.Vector2()
    function click(e) {
      const rect = renderer.domElement.getBoundingClientRect()
      pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
      pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1
      raycaster.setFromCamera(pointer, camera)
      const hit = raycaster.intersectObjects(points.children)[0]
      if (hit) onSelect?.(pointData.get(hit.object))
    }
    renderer.domElement.addEventListener('click', click)

    function resize() {
      const width = mount.clientWidth
      const height = mount.clientHeight
      camera.aspect = width / Math.max(height, 1)
      camera.updateProjectionMatrix()
      renderer.setSize(width, height)
    }
    resize()
    const resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(mount)

    let frame
    function animate() {
      frame = requestAnimationFrame(animate)
      controls.update()
      renderer.render(scene, camera)
    }
    animate()
    sceneRef.current = { points, pointData }

    return () => {
      cancelAnimationFrame(frame)
      resizeObserver.disconnect()
      renderer.domElement.removeEventListener('click', click)
      controls.dispose()
      renderer.dispose()
      earth.geometry.dispose()
      earth.material.dispose()
      if (mount.contains(renderer.domElement)) mount.removeChild(renderer.domElement)
      sceneRef.current = null
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const state = sceneRef.current
    if (!state) return
    while (state.points.children.length) {
      const child = state.points.children.pop()
      child.geometry?.dispose()
      child.material?.dispose()
    }
    state.pointData.clear()
    for (const satellite of satellites || []) {
      const az = satellite.azimuth_deg * Math.PI / 180
      const el = satellite.elevation_deg * Math.PI / 180
      const point = new THREE.Mesh(
        new THREE.SphereGeometry(0.035, 12, 12),
        new THREE.MeshBasicMaterial({ color: CATEGORY_COLOR[satellite.category] ?? CATEGORY_COLOR.Other })
      )
      point.position.set(Math.cos(el) * Math.sin(az) * 1.12, Math.sin(el) * 1.12, Math.cos(el) * Math.cos(az) * 1.12)
      state.points.add(point)
      state.pointData.set(point, satellite)

      if (showLOS) {
        const line = new THREE.Line(
          new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, 0), point.position]),
          new THREE.LineBasicMaterial({ color: point.material.color, transparent: true, opacity: 0.35 })
        )
        state.points.add(line)
      }

      if (showLabels) {
        const canvas = document.createElement('canvas')
        canvas.width = 256
        canvas.height = 48
        const context = canvas.getContext('2d')
        context.font = '22px JetBrains Mono, monospace'
        context.fillStyle = '#cddce3'
        context.fillText(shortLabel(satellite.name), 4, 30)
        const label = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(canvas), transparent: true }))
        label.scale.set(0.55, 0.1, 1)
        label.position.copy(point.position).multiplyScalar(1.12)
        state.points.add(label)
      }
    }

    // Orbit arcs: real SGP4-propagated az/el track per satellite, batch-
    // fetched for everything currently plotted (not just a clicked one).
    // Points below the horizon are skipped so arcs don't cut through Earth;
    // a satellite dipping below horizon within the window just breaks its
    // line into separate segments rather than joining across the gap.
    if (showOrbits && tracks) {
      for (const satellite of satellites || []) {
        const trackEntry = tracks[String(satellite.norad_id)]
        if (!trackEntry?.points?.length) continue
        const color = CATEGORY_COLOR[satellite.category] ?? CATEGORY_COLOR.Other
        let segment = []
        const flushSegment = () => {
          if (segment.length > 1) {
            const line = new THREE.Line(
              new THREE.BufferGeometry().setFromPoints(segment),
              new THREE.LineDashedMaterial({ color, transparent: true, opacity: 0.55, dashSize: 0.05, gapSize: 0.03 })
            )
            line.computeLineDistances()
            state.points.add(line)
          }
          segment = []
        }
        for (const p of trackEntry.points) {
          if (p.elevation_deg < 0) { flushSegment(); continue }
          const az = p.azimuth_deg * Math.PI / 180
          const el = p.elevation_deg * Math.PI / 180
          segment.push(new THREE.Vector3(Math.cos(el) * Math.sin(az) * 1.12, Math.sin(el) * 1.12, Math.cos(el) * Math.cos(az) * 1.12))
        }
        flushSegment()
      }
    }
  }, [satellites, showLabels, showLOS, showOrbits, tracks])

  return <div className="skyplot-globe3d" ref={mountRef} aria-label="Interactive 3D Earth sky plot" />
}

export default function SciSkyPlot({ satellites, mask, onMaskChange, catalogSize, location, onSelect }) {
  const [mode, setMode] = useState('2D')
  const [categoryFilter, setCategoryFilter] = useState(
    Object.fromEntries([...CATEGORY_ORDER, 'Other'].map((c) => [c, true]))
  )
  const [showOrbits, setShowOrbits] = useState(false)
  const [showLabels, setShowLabels] = useState(true)
  const [showLOS, setShowLOS] = useState(false)
  const [maskInput, setMaskInput] = useState(String(mask))
  const [fullscreen, setFullscreen] = useState(false)
  const [sphereRotation, setSphereRotation] = useState(0)
  const dragRef = useRef({ active: false, x: 0 })

  const [tracks, setTracks] = useState(null)
  const [tracksState, setTracksState] = useState('idle')

  const visibleSats = useMemo(
    () => (satellites || []).filter((s) => categoryFilter[s.category ?? 'Other']),
    [satellites, categoryFilter]
  )

  const project = mode === '3D' ? project3D : project2D

  function toggleCategory(c) {
    setCategoryFilter((f) => ({ ...f, [c]: !f[c] }))
  }

  function applyMask(value) {
    const v = Math.max(0, Math.min(90, Number(value) || 0))
    setMaskInput(String(v))
    onMaskChange(v)
  }

  function handleReset() {
    setCategoryFilter(Object.fromEntries([...CATEGORY_ORDER, 'Other'].map((c) => [c, true])))
    setShowOrbits(false)
    setShowLabels(true)
    setShowLOS(false)
    setMode('2D')
    setSphereRotation(0)
    applyMask(10)
  }

  function handleDotClick(sat) {
    onSelect?.(sat)
  }

  // Orbits toggle fetches real SGP4 tracks for every currently-visible
  // satellite at once (one batched request), not just a satellite you click
  // — that's what lets every plotted point show its own orbit arc, matching
  // a real sky-dome view rather than a single highlighted track.
  useEffect(() => {
    if (!showOrbits || !location) { setTracks(null); setTracksState('idle'); return }
    let cancelled = false
    setTracksState('loading')
    api.spaceScienceSatSkyTracks({ lat: location.lat, lon: location.lon, minElevation: mask, windowMin: 25 })
      .then((result) => { if (!cancelled) { setTracks(result.tracks); setTracksState('done') } })
      .catch(() => { if (!cancelled) { setTracks(null); setTracksState('error') } })
    return () => { cancelled = true }
  }, [showOrbits, location?.lat, location?.lon, mask]) // eslint-disable-line react-hooks/exhaustive-deps

  const trackPolylines2D = useMemo(() => {
    if (!tracks) return []
    return Object.entries(tracks).map(([noradId, entry]) => {
      const segments = []
      let current = []
      for (const p of entry.points) {
        if (p.elevation_deg < 0) {
          if (current.length > 1) segments.push(current)
          current = []
          continue
        }
        current.push(project(p.azimuth_deg, p.elevation_deg))
      }
      if (current.length > 1) segments.push(current)
      return { noradId, category: entry.category, segments }
    })
  }, [tracks, mode]) // eslint-disable-line react-hooks/exhaustive-deps

  const rings2D = [0, 30, 60].map((el) => ({ el, ...ringPath2D(el) }))
  const rings3D = [0, 30, 60].map((el) => ({ el, ...ringEllipse3D(el) }))
  const maskRing2D = mask > 0 ? ringPath2D(mask) : null
  const maskRing3D = mask > 0 ? ringEllipse3D(mask) : null

  function startSphereDrag(e) {
    if (mode !== '3D') return
    dragRef.current = { active: true, x: e.clientX }
    e.currentTarget.setPointerCapture?.(e.pointerId)
  }

  function moveSphereDrag(e) {
    if (!dragRef.current.active) return
    const delta = e.clientX - dragRef.current.x
    dragRef.current.x = e.clientX
    setSphereRotation((value) => value + delta * 0.7)
  }

  function stopSphereDrag() {
    dragRef.current.active = false
  }

  return (
    <article className={`panel skyplot-panel ${fullscreen ? 'skyplot-fullscreen' : ''}`}>
      <div className="skyplot-head">
        <div>
          <p className="eyebrow">SKY PLOT</p>
          <h2>{visibleSats.length} of {catalogSize ?? '—'} satellites shown</h2>
        </div>
        <div className="skyplot-head-right">
          <span className="live-badge small"><i /> LIVE</span>
          <div className="skyplot-mode-toggle">
            <button className={mode === '2D' ? 'active' : ''} onClick={() => setMode('2D')}>2D</button>
            <button className={mode === '3D' ? 'active' : ''} onClick={() => setMode('3D')}>3D</button>
          </div>
          <button type="button" className="skyplot-action skyplot-reset" onClick={handleReset}>Reset</button>
          <button type="button" className="skyplot-action skyplot-fullscreen-action" onClick={() => setFullscreen((f) => !f)}>{fullscreen ? 'Exit' : 'Fullscreen'}</button>
        </div>
      </div>

      <div className="skyplot-toolbar">
        {[...CATEGORY_ORDER, 'Other'].filter((c) => (satellites || []).some((s) => (s.category ?? 'Other') === c) || categoryFilter[c] === false).map((c) => (
          <button
            key={c}
            className={`category-chip ${categoryFilter[c] ? '' : 'off'}`}
            style={{ borderColor: CATEGORY_COLOR[c], color: categoryFilter[c] ? CATEGORY_COLOR[c] : undefined }}
            onClick={() => toggleCategory(c)}
          >
            {c}
          </button>
        ))}
        <span className="toolbar-divider" />
        <button className={`toggle-pill ${showOrbits ? 'active' : ''}`} onClick={() => setShowOrbits((v) => !v)}>Orbits</button>
        <button className={`toggle-pill ${showLabels ? 'active' : ''}`} onClick={() => setShowLabels((v) => !v)}>Labels</button>
        <button className={`toggle-pill ${showLOS ? 'active' : ''}`} onClick={() => setShowLOS((v) => !v)}>LOS</button>
        <span className="toolbar-divider" />
        <div className="mask-control">
          {MASK_PRESETS.map((v) => (
            <button key={v} className={mask === v ? 'active' : ''} onClick={() => applyMask(v)}>{v}°</button>
          ))}
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

      {mode === '3D' ? <Globe3D satellites={visibleSats} tracks={tracks} onSelect={handleDotClick} showLabels={showLabels} showLOS={showLOS} showOrbits={showOrbits} /> : <svg
        className={`skyplot-svg ${mode === '3D' ? 'skyplot-rotatable' : ''}`}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        onPointerDown={startSphereDrag}
        onPointerMove={moveSphereDrag}
        onPointerUp={stopSphereDrag}
        onPointerCancel={stopSphereDrag}
      >
        <defs>
          <radialGradient id="skyplot-earth-gradient" cx="35%" cy="28%" r="72%">
            <stop offset="0%" stopColor="#3c8bb0" stopOpacity=".55" />
            <stop offset="58%" stopColor="#155276" stopOpacity=".72" />
            <stop offset="100%" stopColor="#061628" stopOpacity=".92" />
          </radialGradient>
        </defs>
        <g transform={mode === '3D' ? `rotate(${sphereRotation} ${C} ${C})` : undefined}>
        {mode === '3D' && <circle cx={C} cy={C} r={R} className="skyplot-earth" />}
        {mode === '2D' ? (
          <>
            {rings2D.map((ring) => (
              <circle key={ring.el} cx={ring.cx} cy={ring.cy} r={ring.r} className="skyplot-ring" />
            ))}
            {maskRing2D && <circle cx={maskRing2D.cx} cy={maskRing2D.cy} r={maskRing2D.r} className="skyplot-mask-ring" />}
            {rings2D.map((ring) => (
              <text key={`lbl-${ring.el}`} x={C + 4} y={C - ring.r - 4} className="skyplot-ring-label">{ring.el}°</text>
            ))}
          </>
        ) : (
          <>
            {rings3D.map((ring) => (
              <ellipse key={ring.el} cx={ring.cx} cy={ring.cy} rx={ring.rx} ry={ring.ry} className="skyplot-ring" />
            ))}
            {maskRing3D && <ellipse cx={maskRing3D.cx} cy={maskRing3D.cy} rx={maskRing3D.rx} ry={maskRing3D.ry} className="skyplot-mask-ring" />}
          </>
        )}

        <text x={C} y={mode === '3D' ? C - R * 0.92 - 16 : C - R - 14} className="skyplot-cardinal">N</text>
        <text x={mode === '3D' ? C + R + 12 : C + R + 14} y={C + 5} className="skyplot-cardinal">E</text>
        <text x={C} y={mode === '3D' ? C + R * TILT * 0.25 + 26 : C + R + 24} className="skyplot-cardinal">S</text>
        <text x={mode === '3D' ? C - R - 12 : C - R - 14} y={C + 5} className="skyplot-cardinal">W</text>

        {showOrbits && trackPolylines2D.map(({ noradId, category, segments }) => (
          <g key={noradId}>
            {segments.map((seg, i) => (
              <polyline
                key={i}
                points={seg.map((p) => `${p.x},${p.y}`).join(' ')}
                className="skyplot-track"
                style={{ stroke: CATEGORY_COLOR[category] ?? CATEGORY_COLOR.Other }}
              />
            ))}
          </g>
        ))}

        {visibleSats.map((sat) => {
          const p = project(sat.azimuth_deg, sat.elevation_deg)
          const color = CATEGORY_COLOR[sat.category] ?? CATEGORY_COLOR.Other
          const radius = 5 * (p.scale ?? 1)
          return (
            <g key={sat.norad_id} className="skyplot-sat" onClick={() => handleDotClick(sat)}>
              {showLOS && <line x1={C} y1={C} x2={p.x} y2={p.y} className="skyplot-los" style={{ stroke: color }} />}
              <circle cx={p.x} cy={p.y} r={radius} fill={color} stroke="#04121a" strokeWidth="1" />
              {showLabels && <text x={p.x + radius + 3} y={p.y + 3} className="skyplot-label">{shortLabel(sat.name)}</text>}
            </g>
          )
        })}
        </g>
      </svg>}

      {showOrbits && (
        <div className="skyplot-track-note">
          {tracksState === 'loading' && 'Propagating orbit arcs for every plotted satellite (SGP4, ±25 min)…'}
          {tracksState === 'done' && `Showing real orbit arcs for ${Object.keys(tracks || {}).length} satellites (±25 min, SGP4-propagated).`}
          {tracksState === 'error' && 'Could not compute orbit arcs — CelesTrak may be rate-limited this cycle.'}
        </div>
      )}
      <small className="skyplot-source">Live azimuth/elevation for {location?.label ?? 'the selected location'}</small>
    </article>
  )
}
