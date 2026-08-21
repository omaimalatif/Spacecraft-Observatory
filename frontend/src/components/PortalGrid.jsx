import PortalCard from './PortalCard.jsx'

const PORTALS = [
  {
    num: '01', color: '#C9A227', title: 'Global Space Assets', image: 'https://images-assets.nasa.gov/image/PIA04921/PIA04921~orig.jpg',
    href: '#/global-space-assets',
    desc: "A real-time view of humanity's presence in orbit — every tracked object, by regime, altitude, inclination and country.",
    tags: ['3D orbital view', 'Debris tracking', 'Country map'],
    metrics: [{ value: '91', label: 'Countries' }, { value: '278', label: 'Operators' }],
  },
  {
    num: '02', color: '#8FE3C7',  title: 'Earth Observation', image: 'https://images.unsplash.com/photo-1500534623283-312aade485b7?auto=format&fit=crop&w=900&q=85',
    desc: 'Observing our planet — imaging, climate and land monitoring missions.',
    tags: ['305 satellites', '27 agencies'],
  },
  {
    num: '03', color: '#E68FBF', title: 'Navigation Systems', image: 'https://images.unsplash.com/photo-1517976487492-5750f3195933?auto=format&fit=crop&w=900&q=85',
    desc: 'Global positioning — GPS, GLONASS, Galileo, BeiDou constellations.',
    tags: ['6 constellations', '225 satellites'],
  },
  {
    num: '04', color: '#FFB454', title: 'Communication', image: 'https://images.unsplash.com/photo-1516849841032-87cbac4d88f7?auto=format&fit=crop&w=900&q=85',
    desc: 'Enabling global connectivity across GEO, MEO and LEO fleets.',
    tags: ['530+ active', '100% coverage'],
  },
  {
    num: '05', color: '#C9A227', title: 'Meteorological & Environmental', image: 'https://images.unsplash.com/photo-1499346030926-9a72daac6c63?auto=format&fit=crop&w=900&q=85',
    desc: 'Monitoring weather and climate from geostationary and polar orbits.',
    tags: ['160+ satellites', '24/7 monitoring'],
  },
  {
    num: '06', color: '#E68FBF', title: 'Space Science & Exploration', image: 'https://images.unsplash.com/photo-1444703686981-a3abbc4d4fe3?auto=format&fit=crop&w=900&q=85',
    desc: 'Discovering the universe — telescopes, probes and confirmed exoplanets.',
    tags: ['120+ missions', '1000+ exoplanets'],
  },
  {
    num: '07', color: '#FFB454',  title: 'Human Spaceflight', image: 'https://images.unsplash.com/photo-1614728894747-a83421e2b9c9?auto=format&fit=crop&w=900&q=85',
    desc: 'Human presence in space — stations, crew and continuous presence.',
    tags: ['2 stations', '400+ humans flown'],
  },
  {
    num: '08', color: '#8FE3C7', title: 'CubeSat & Small Satellites', image: 'https://images.unsplash.com/photo-1517976547714-720226b864c1?auto=format&fit=crop&w=900&q=85',
    desc: 'Innovating the future — the rise of small, low-cost satellite missions.',
    tags: ['2,000+ in orbit', '60+ countries'],
  },
]

export default function PortalGrid() {
  return (
    <section className="section" id="portals">
      <div className="section-head">
        <h2>Explore all mission portals</h2>
        <span className="tag">02 — 08 · specialized views</span>
      </div>
      <div className="portals-grid">
        {PORTALS.map((p) => <PortalCard key={p.num} {...p} />)}
      </div>
    </section>
  )
}
