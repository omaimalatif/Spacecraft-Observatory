import { useEffect, useState } from 'react'

const PORTAL_TITLES = [
  'Global Space Assets',
  'Earth Observation',
  'Navigation Systems',
  'Communication',
  'Meteorological & Environmental',
  'Space Science & Exploration',
  'Human Spaceflight',
  'CubeSat & Small Satellites',
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

  useEffect(() => {
    const timer = setInterval(() => {
      setMessageIndex((current) => (current + 1) % HERO_MESSAGES.length)
    }, 5000)
    return () => clearInterval(timer)
  }, [])

  return (
    <section className="hero" id="top">
      <header className="landing-nav">
        <a className="landing-brand" href="#top"><img className="landing-brand-logo" src="/ncgsa-logo.png" alt="NCGSA logo" /><strong>NSO</strong><span>SPACECRAFT OBSERVATORY</span></a>
        <div className="landing-links"><a className="portal-link" href="#portals">Portals</a><a className="visibility-link" href="#visibility">Visibility</a><details className="about-menu"><summary>About</summary><div className="about-dropdown"><strong>NCGSA Spacecraft Observatory</strong><p>Explore the systems, missions and objects shaping humanity's presence in space.</p><span>8 mission portals</span><div className="about-portals">{PORTAL_TITLES.map((title) => <a key={title} href="#portals">{title}</a>)}</div></div></details></div>
      </header>
      <div className="hero-title">
       
        <h1>NCGSA<br /><em>SPACECRAFT</em> <br />OBSERVATORY</h1>
        <p className="lead hero-message" key={messageIndex} aria-live="polite">{HERO_MESSAGES[messageIndex]}</p>
      </div>
      <div className="hero-earth" role="img" aria-label="Earth from space" />
    </section>
  )
}
