import { useEffect, useRef, useState } from 'react'

const PORTALS = [
  { title: 'Global Space Assets', href: '#/global-space-assets' },
  { title: 'Earth Observation Satellites', href: '#/earth-observation' },
  { title: 'Navigation Systems', href: '#/navigation-systems' },
  { title: 'Communication', href: '#portals' },
  { title: 'Meteorological & Environmental', href: '#portals' },
  { title: 'Live Space Science Tracking', href: '#/space-science' },
  { title: 'Human Spaceflight', href: '#portals' },
  { title: 'CubeSat & Small Satellites', href: '#portals' },
]

const HERO_MESSAGES = [
  'Track the spacecraft, satellites and missions shaping our presence in orbit.',
  'Explore Earth observation systems that help us understand our changing planet.',
  'Follow navigation, communication and weather constellations around Earth.',
  'Discover the science, exploration and human missions reaching beyond our planet.',
  'Use live orbital data to see what is overhead from any location on Earth.',
]

export default function Hero() {
  const [messageIndex, setMessageIndex] = useState(0)
  const linksRef = useRef(null)

  useEffect(() => {
    const timer = setInterval(() => {
      setMessageIndex((current) => (current + 1) % HERO_MESSAGES.length)
    }, 5000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    function closeMenus(event) {
      if (linksRef.current?.contains(event.target)) return
      linksRef.current?.querySelectorAll('details[open]').forEach((menu) => menu.removeAttribute('open'))
    }
    document.addEventListener('click', closeMenus)
    return () => document.removeEventListener('click', closeMenus)
  }, [])

  return (
    <section className="hero" id="top">
      <header className="landing-nav">
        <a className="landing-brand" href="#top"><img className="landing-brand-logo" src="/ncgsa-logo.png" alt="NCGSA logo" /><strong>NSO</strong><span>SPACECRAFT OBSERVATORY</span></a>
        <div className="landing-links" ref={linksRef}><details className="about-menu portal-menu"><summary>Portals</summary><div className="about-dropdown"><strong>Mission portals</strong><span>Explore all dashboards</span><div className="about-portals">{PORTALS.map((portal) => <a key={portal.title} href={portal.href}>{portal.title}</a>)}</div></div></details><a className="visibility-link" href="#visibility">Track satellites worldwide</a><details className="about-menu"><summary>About</summary><div className="about-dropdown"><strong>NCGSA Spacecraft Observatory</strong><p>Explore the systems, missions and objects shaping humanity's presence in space.</p><span>8 mission portals</span><div className="about-portals">{PORTALS.map((portal) => <a key={portal.title} href={portal.href}>{portal.title}</a>)}</div></div></details></div>
      </header>
      <div className="hero-title">
       
        <h1><span className="title-reflection">N</span>CGSA<br /><em><span className="title-reflection">S</span>PACECRAFT</em> <br /><span className="title-reflection">O</span>BSERVATORY</h1>
        <p className="lead hero-message" key={messageIndex} aria-live="polite">{HERO_MESSAGES[messageIndex]}</p>
      </div>
      <div className="hero-earth" role="img" aria-label="Earth beneath a satellite-filled night sky" />
    </section>
  )
}
