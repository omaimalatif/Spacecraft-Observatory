import { lazy, Suspense, useEffect, useState } from 'react'
import { api } from '../api.js'
import PortalMenu from './PortalMenu.jsx'

const EoGlobe = lazy(() => import('./EoGlobe.jsx'))

const fmt = (n) => n == null ? 'Data unavailable' : new Intl.NumberFormat().format(n)

// Same colors EoGlobe.jsx uses for the on-globe dots, reused here so the KPI
// cards visually match what's plotted below.
const HAZARD_ACCENTS = {
  'Fire Detection': '#ff8a5c',
  'Storm & Weather Tracking': '#ffd166',
  'Flood & Precipitation Monitoring': '#5ec8ff',
  'General Earth Observation': '#8fe3c7',
}

function LiveClock() {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return <span className="live-clock">{now.toISOString().slice(0, 19).replace('T', ' ')} UTC</span>
}

function fromGlobePoint(o) {
  return { ...o, hasLivePosition: true }
}

export default function EarthObservation() {
  const [types, setTypes] = useState(null)
  const [typesError, setTypesError] = useState(null)
  const [selected, setSelected] = useState(null)

  useEffect(() => {
    api.earthObservationTypes()
      .then((d) => { setTypes(d); setTypesError(null) })
      .catch((err) => setTypesError(err.message || 'Data unavailable'))
  }, [])

  return (
    <main className="eo-page">
      <header className="eo-header">
        <a href="#" className="wordmark"><img className="assets-brand-logo" src="/ncgsa-logo.png" alt="NCGSA logo" /><span>NCGSA</span><small>SPACECRAFT OBSERVATORY</small></a>
        <nav>
          <a href="#">← Observatory home</a>
          <PortalMenu />
          <a className="active">02 Earth Observation Satellites</a>
        </nav>
        <div className="eo-header-right">
          <LiveClock />
          <span className="live-badge" role="status"><i /> LIVE</span>
        </div>
      </header>

      <section className="eo-intro">
        <div>
          <p className="eyebrow">PORTAL 02 / MISSION OVERVIEW</p>
          <h1>Earth Observation <em>Satellites</em></h1>
          <p>
            Which satellites are watching Earth for hazards — live 3D orbital positions of the
            spacecraft that detect fires, storms, floods and other events. This shows the
            satellites themselves, not the events they detect.
          </p>
        </div>
      </section>

      <section className="eo-kpis eo-hazard-kpis">
        {typesError ? (
          <article style={{ gridColumn: '1 / -1' }}><span>Satellite categories</span><strong className="unavailable">{typesError}</strong></article>
        ) : !types ? (
          <p className="eo-empty">Loading satellite categories…</p>
        ) : (
          <>
            <article style={{ '--accent': '#79d8ff' }}>
              <span>EO satellites tracked</span>
              <strong>{fmt(types.total)}</strong>
              <small>CelesTrak resource + weather groups</small>
            </article>
            {types.types.map((t) => (
              <article key={t.label} style={{ '--accent': HAZARD_ACCENTS[t.label] }}>
                <span>{t.label}</span>
                <strong>{fmt(t.total)}</strong>
                <small>{fmt(t.active)} active</small>
              </article>
            ))}
          </>
        )}
      </section>

      <section className="eo-globe-section">
        <article className="globe-card panel">
          <div className="panel-head">
            <div><p className="eyebrow">ORBITAL VIEW · CESIUM 3D</p><h2>Earth observation satellites in orbit</h2></div>
            <span title="Live SGP4-propagated positions, CelesTrak GROUP=resource + GROUP=weather">Live SGP4-propagated positions</span>
          </div>
          <Suspense fallback={<div className="globe-loading" role="status">Loading orbital view…</div>}>
            <EoGlobe selected={selected} onSelect={(o) => setSelected(fromGlobePoint(o))} onClose={() => setSelected(null)} />
          </Suspense>
        </article>
      </section>

      <footer className="eo-footer">
        Data attribution: <a href="https://celestrak.org/" target="_blank" rel="noreferrer">CelesTrak GP</a> (live satellite positions, SGP4-propagated) ·{' '}
        <a href="https://celestrak.org/satcat/" target="_blank" rel="noreferrer">CelesTrak SATCAT</a> (active/inactive status). Hazard-focus categories are a
        best-effort classification from each satellite's mission name against known patterns (e.g. TERRA/AQUA/SUOMI NPP → Fire Detection) —
        not an authoritative purpose registry. Indicative subset of CelesTrak's own mission-category groups, not a complete EO satellite census.
      </footer>
    </main>
  )
}
