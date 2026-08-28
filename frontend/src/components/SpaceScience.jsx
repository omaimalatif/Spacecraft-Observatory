import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { api } from '../api.js'
import PortalMenu from './PortalMenu.jsx'

const fmt = (n) => n == null ? 'Unavailable' : new Intl.NumberFormat().format(n)

// Real semi-major axes in AU, used only to decide visual placement — the
// scene compresses distance (see auToScene) so all 8 planets fit on screen
// at once. This is a deliberate "not to scale" simplification, disclosed
// in the UI rather than hidden.
const PLANET_STYLE = {
  Mercury: { color: 0x9a9a9a, size: 0.9 },
  Venus: { color: 0xe8cfa0, size: 1.3 },
  Earth: { color: 0x4f9eff, size: 1.4 },
  Mars: { color: 0xd6633f, size: 1.1 },
  Jupiter: { color: 0xd9b487, size: 3.2 },
  Saturn: { color: 0xe6c98a, size: 2.8 },
  Uranus: { color: 0x9fe0e6, size: 2.1 },
  Neptune: { color: 0x5a7fe6, size: 2.0 },
}

function auToScene(au) {
  // Compressed radial scale so Neptune (30 AU) and Mercury (0.39 AU) are
  // both visible and distinguishable — NOT a linear/true-to-scale distance.
  return 6 + Math.log(au + 1) * 9
}

function LiveClock() {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return <span className="live-clock">{now.toISOString().slice(0, 19).replace('T', ' ')} UTC</span>
}

function StatusDot({ status }) {
  const cls = status === 'ONLINE' ? 'ok' : status === 'NOT CONNECTED' ? 'off' : 'warn'
  return <span className={`status-dot ${cls}`}><i />{status}</span>
}

export default function SpaceScience() {
  const mountRef = useRef(null)
  const sceneRef = useRef(null)
  const objectsRef = useRef(new Map()) // name -> {mesh, data}

  const [solarSystem, setSolarSystem] = useState(null)
  const [solarError, setSolarError] = useState(null)
  const [spacecraft, setSpacecraft] = useState(null)
  const [neo, setNeo] = useState(null)
  const [neoError, setNeoError] = useState(null)
  const [status, setStatus] = useState(null)
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(true)

  // --- fetch real data ---
  useEffect(() => {
    api.spaceScienceSolarSystem()
      .then((d) => { setSolarSystem(d); setSolarError(null) })
      .catch((err) => setSolarError(err.message))
      .finally(() => setLoading(false))
    api.spaceScienceSpacecraft().then(setSpacecraft).catch(() => setSpacecraft(null))
    api.spaceScienceNeo(7).then((d) => { setNeo(d); setNeoError(null) }).catch((err) => setNeoError(err.message))
    api.spaceScienceStatus().then(setStatus).catch(() => setStatus(null))
  }, [])

  // --- init Three.js scene once ---
  useEffect(() => {
    if (!mountRef.current || sceneRef.current) return
    const container = mountRef.current
    const width = container.clientWidth, height = container.clientHeight

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 2000)
    camera.position.set(0, 70, 130)

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setSize(width, height)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    container.appendChild(renderer.domElement)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.06
    controls.minDistance = 20
    controls.maxDistance = 400

    scene.add(new THREE.AmbientLight(0x445566, 1.1))
    const sunLight = new THREE.PointLight(0xfff2d6, 3.2, 0, 0)
    scene.add(sunLight)

    // Sun
    const sun = new THREE.Mesh(
      new THREE.SphereGeometry(4.2, 32, 32),
      new THREE.MeshBasicMaterial({ color: 0xffcf6b })
    )
    scene.add(sun)
    const sunGlow = new THREE.Mesh(
      new THREE.SphereGeometry(6, 32, 32),
      new THREE.MeshBasicMaterial({ color: 0xffb347, transparent: true, opacity: 0.18 })
    )
    scene.add(sunGlow)

    // Starfield background
    const starGeo = new THREE.BufferGeometry()
    const starCount = 1500
    const starPos = new Float32Array(starCount * 3)
    for (let i = 0; i < starCount; i++) {
      const r = 600 + Math.random() * 400
      const theta = Math.random() * Math.PI * 2
      const phi = Math.acos(2 * Math.random() - 1)
      starPos[i * 3] = r * Math.sin(phi) * Math.cos(theta)
      starPos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta)
      starPos[i * 3 + 2] = r * Math.cos(phi)
    }
    starGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3))
    scene.add(new THREE.Points(starGeo, new THREE.PointsMaterial({ color: 0xaaccff, size: 1.1, sizeAttenuation: true })))

    const raycaster = new THREE.Raycaster()
    const pointer = new THREE.Vector2()
    function onClick(e) {
      const rect = renderer.domElement.getBoundingClientRect()
      pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
      pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1
      raycaster.setFromCamera(pointer, camera)
      const meshes = [...objectsRef.current.values()].map((o) => o.mesh)
      const hit = raycaster.intersectObjects(meshes)[0]
      if (hit) {
        const found = [...objectsRef.current.values()].find((o) => o.mesh === hit.object)
        if (found) setSelected(found.data)
      }
    }
    renderer.domElement.addEventListener('click', onClick)

    let raf
    function animate() {
      raf = requestAnimationFrame(animate)
      controls.update()
      renderer.render(scene, camera)
    }
    animate()

    function onResize() {
      const w = container.clientWidth, h = container.clientHeight
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      renderer.setSize(w, h)
    }
    window.addEventListener('resize', onResize)

    sceneRef.current = { scene, camera, renderer, controls }
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', onResize)
      renderer.domElement.removeEventListener('click', onClick)
      controls.dispose()
      renderer.dispose()
      if (container.contains(renderer.domElement)) container.removeChild(renderer.domElement)
      sceneRef.current = null
    }
  }, [])

  // --- place planets once solar-system data arrives ---
  useEffect(() => {
    if (!sceneRef.current || !solarSystem) return
    const { scene } = sceneRef.current

    for (const body of solarSystem.bodies) {
      if (body.name === 'Sun') continue
      const style = PLANET_STYLE[body.name] || { color: 0xbbbbbb, size: 1 }
      const auDist = Math.hypot(body.x_au, body.y_au, body.z_au)
      const sceneDist = auToScene(auDist)
      const angle = Math.atan2(body.y_au, body.x_au)

      const mesh = new THREE.Mesh(
        new THREE.SphereGeometry(style.size, 24, 24),
        new THREE.MeshStandardMaterial({ color: style.color, roughness: 0.7 })
      )
      mesh.position.set(Math.cos(angle) * sceneDist, 0, Math.sin(angle) * sceneDist)
      scene.add(mesh)

      // faint orbit ring for context
      const ring = new THREE.Mesh(
        new THREE.RingGeometry(sceneDist - 0.05, sceneDist + 0.05, 128),
        new THREE.MeshBasicMaterial({ color: 0x2c4a5e, side: THREE.DoubleSide, transparent: true, opacity: 0.35 })
      )
      ring.rotation.x = Math.PI / 2
      scene.add(ring)

      objectsRef.current.set(body.name, {
        mesh,
        data: { kind: 'planet', ...body, distance_au: auDist },
      })
    }
  }, [solarSystem])

  // --- place spacecraft once resolved ---
  useEffect(() => {
    if (!sceneRef.current || !spacecraft) return
    const { scene } = sceneRef.current

    for (const mission of spacecraft.missions) {
      if (!mission.position) continue
      const p = mission.position
      const auDist = Math.hypot(p.x_au, p.y_au, p.z_au)
      const sceneDist = auToScene(auDist)
      const angle = Math.atan2(p.y_au, p.x_au)

      const mesh = new THREE.Mesh(
        new THREE.OctahedronGeometry(0.9),
        new THREE.MeshStandardMaterial({ color: 0xff6ec7, emissive: 0x551133, roughness: 0.4 })
      )
      mesh.position.set(Math.cos(angle) * sceneDist, 0, Math.sin(angle) * sceneDist)
      scene.add(mesh)

      objectsRef.current.set(mission.key, {
        mesh,
        data: { kind: 'spacecraft', ...mission, distance_au: auDist },
      })
    }
  }, [spacecraft])

  const hazardousNeo = neo?.hazardous_count ?? null
  const resolvedSpacecraft = spacecraft?.resolved_count ?? null
  const totalSpacecraft = spacecraft?.total_count ?? null

  return (
    <main className="sci-page">
      <header className="sci-header">
        <a href="#" className="wordmark"><img className="assets-brand-logo" src="/ncgsa-logo.png" alt="NCGSA logo" /><span>NCGSA</span><small>SPACECRAFT OBSERVATORY</small></a>
        <nav><a href="#">← Observatory home</a><PortalMenu /><a className="active">06 Space Science</a><a href="#sci-sources">Data Sources</a></nav>
        <div className="sci-header-right">
          <LiveClock />
          <span className="live-badge" role="status"><i /> LIVE</span>
        </div>
      </header>

      <section className="sci-intro">
        <p className="eyebrow">PORTAL 06 / MISSION OVERVIEW</p>
        <h1>Space Science &amp; <em>Exploration</em></h1>
        <p>What humanity's scientific missions are discovering beyond Earth.</p>
      </section>

      <section className="sci-kpis">
        <article><span>Bodies tracked</span><strong className={solarError ? 'unavailable' : ''}>{solarError ? 'Unavailable' : fmt(solarSystem?.bodies?.length)}</strong><small>Sun + 8 planets · Horizons</small></article>
        <article><span>Spacecraft resolved</span><strong className={totalSpacecraft == null ? 'unavailable' : ''}>{resolvedSpacecraft != null ? `${resolvedSpacecraft} / ${totalSpacecraft}` : 'Unavailable'}</strong><small>EPHEMERIS-DERIVED positions</small></article>
        <article><span>NEOs (7 days)</span><strong className={neoError ? 'unavailable' : ''}>{neoError ? 'Unavailable' : fmt(neo?.count)}</strong></article>
        <article><span>Potentially hazardous</span><strong className={hazardousNeo == null ? 'unavailable' : ''}>{fmt(hazardousNeo)}</strong></article>
        <article><span>Data services</span><strong>2</strong></article>
      </section>

      <section className="sci-command-grid">
        <article className="sci-scene-card panel">
          <div className="panel-head">
            <div><p className="eyebrow">3D SOLAR SYSTEM</p><h2>Live ephemeris view</h2></div>
            <span>Distances compressed for visibility — not to scale</span>
          </div>
          <div className="sci-scene-stage" ref={mountRef}>
            {loading && <div className="sci-scene-loading">Calculating ephemerides…</div>}
            {solarError && <div className="sci-scene-loading">{solarError}</div>}
          </div>
          <p className="sci-scene-note">Drag to rotate · scroll to zoom · click a planet or spacecraft for details.</p>
        </article>

        <aside className="panel sci-detail-panel">
          <p className="eyebrow">OBJECT DETAIL</p>
          {!selected ? (
            <p className="sci-empty">Click any planet or spacecraft in the 3D view to inspect its calculated position.</p>
          ) : (
            <div className="sci-detail">
              <h3>{selected.name}</h3>
              {selected.kind === 'spacecraft' && (
                <>
                  <p className="sci-detail-row"><span>Agency</span><b>{selected.agency}</b></p>
                  <p className="sci-detail-row"><span>Launched</span><b>{selected.launch_date}</b></p>
                  <p className="sci-detail-row"><span>Target</span><b>{selected.target}</b></p>
                  <p className="sci-detail-row"><span>Status</span><b>{selected.status}</b></p>
                </>
              )}
              <p className="sci-detail-row"><span>Distance from Sun</span><b>{selected.distance_au?.toFixed(3)} AU</b></p>
              <p className="sci-detail-row"><span>Epoch</span><b>{selected.calendar_date}</b></p>
              <p className="sci-badge">EPHEMERIS-DERIVED</p>
            </div>
          )}
        </aside>
      </section>

      <section className="sci-lower-grid">
        <article className="panel">
          <p className="eyebrow">NEAR-EARTH OBJECTS</p>
          <h2>Close approaches — next 7 days</h2>
          {neoError ? <p className="sci-empty">{neoError}</p> : !neo ? <p className="sci-empty">Loading…</p> : neo.objects.length === 0 ? (
            <p className="sci-empty">No close approaches in the next 7 days.</p>
          ) : (
            <div className="sci-neo-list">
              {neo.objects.slice(0, 10).map((n) => (
                <div className="sci-neo-row" key={n.id}>
                  <span className={`hazard-dot ${n.is_potentially_hazardous ? 'hazard' : ''}`} />
                  <span className="name">{n.name}</span>
                  <span className="meta">{n.close_approach_date} · {Number(n.miss_distance_km).toLocaleString(undefined, { maximumFractionDigits: 0 })} km miss</span>
                </div>
              ))}
            </div>
          )}
          <small>{neo?.hazard_label || ''}</small>
        </article>

        <article className="panel">
          <p className="eyebrow">DATA SERVICES</p>
          <h2>Source status</h2>
          {status ? (
            <ul className="sci-status-list">
              {status.services.map((s) => (
                <li key={s.name}>
                  <a href={s.url} target="_blank" rel="noreferrer">{s.name}</a>
                  <StatusDot status={s.status} />
                </li>
              ))}
            </ul>
          ) : <p className="sci-empty">Checking service status…</p>}
          <small>Statuses reflect the most recent real request this session — nothing here is simulated.</small>
        </article>
      </section>

      <footer className="sci-footer">
        Positions are EPHEMERIS-DERIVED (calculated from tracked orbital solutions via <a href="https://ssd.jpl.nasa.gov/horizons/" target="_blank" rel="noreferrer">NASA/JPL Horizons</a>), not live telemetry. NEO data from <a href="https://api.nasa.gov/" target="_blank" rel="noreferrer">NASA NeoWs</a>.
      </footer>
    </main>
  )
}
