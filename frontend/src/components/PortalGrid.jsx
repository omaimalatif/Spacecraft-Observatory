import PortalCard from './PortalCard.jsx'

const PORTALS = [
  {
    color: '#C9A227', title: 'Global Space Assets',
    href: '#/global-space-assets',
    desc: 'Monitor the objects orbiting Earth, including satellites, rocket bodies, and debris. Explore their owners, types, statuses, and orbital regimes through live catalog and tracking data.',
  },
  {
    color: '#8FE3C7',  title: 'Earth Observation',
    href: '#/earth-observation',
    desc: 'Discover the satellites that keep watch over our planet — mapping coastlines, tracking storms, and measuring how land, oceans, and climate are changing over time.',
  },
  {
    color: '#E68FBF', title: 'Navigation Systems',
    href: '#/navigation-systems',
    desc: 'Understand the GPS-like satellite networks that make positioning and timing possible worldwide, including which constellations are visible from your part of the globe right now.',
  },
  {
    color: '#FFB454', title: 'Communication',
    desc: 'Explore the satellites that carry phone calls, internet, TV, and data across the planet — from geostationary giants to fast-growing broadband constellations in low orbit.',
  },
  {
    color: '#C9A227', title: 'Meteorological & Environmental',
    desc: 'Follow the missions that forecast the weather and monitor the environment, from daily storm tracking to long-term climate and pollution measurements from space.',
  },
  {
    color: '#E68FBF', title: 'Space Science & Exploration',
    href: '#/space-science',
    desc: 'Meet the telescopes, probes, and observatories reaching beyond Earth — studying distant galaxies, other planets, and the origins of the universe itself.',
  },
  {
    color: '#FFB454',  title: 'Human Spaceflight',
    desc: 'Track the crewed missions and orbital stations that keep people living and working in space, along with the astronauts and vehicles that support them.',
  },
  {
    color: '#8FE3C7', title: 'CubeSat & Small Satellites',
    desc: 'Learn about the new generation of compact, low-cost spacecraft that are making it easier than ever for universities, startups, and small nations to reach orbit.',
  },
]

export default function PortalGrid() {
  return (
    <section className="section" id="portals">
      <div className="section-head">
        <h2>Explore all mission portals</h2>
      </div>
      <div className="portals-grid">
        {PORTALS.map((p) => <PortalCard key={p.title} {...p} />)}
      </div>
    </section>
  )
}
