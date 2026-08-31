import { useEffect, useRef } from 'react'

const PORTALS = [
  { title: 'Global Space Assets', href: '#/global-space-assets' },
  { title: 'Earth Observation Satellites', href: '#/earth-observation' },
  { title: 'Navigation Satellites', href: '#/navigation-systems' },
  { title: 'Communication Satellites', href: '#/communication' },
  { title: 'Meteorological & Environmental Satellites', href: '#/meteorological' },
  { title: 'Space Science Satellites', href: '#/space-science' },
  { title: 'Human Spaceflight Satellites', href: '#/human-spaceflight' },
  { title: 'CubeSat & Small Satellites', href: '#/cubesat' },
]

export default function PortalMenu() {
  const menuRef = useRef(null)

  useEffect(() => {
    function closeOnOutsideClick(event) {
      if (!menuRef.current?.contains(event.target)) menuRef.current?.removeAttribute('open')
    }

    document.addEventListener('pointerdown', closeOnOutsideClick)
    return () => document.removeEventListener('pointerdown', closeOnOutsideClick)
  }, [])

  function closeMenu() {
    menuRef.current?.removeAttribute('open')
  }

  return (
    <details ref={menuRef} className="eo-portal-menu">
      <summary>Portals</summary>
      <div className="eo-portal-dropdown">
        <strong>Mission portals</strong>
        <span>Explore all dashboards</span>
        <div className="eo-portal-links">
          {PORTALS.map((portal) => portal.href ? (
            <a key={portal.title} href={portal.href} onClick={closeMenu}>{portal.title}</a>
          ) : (
            <span key={portal.title} aria-disabled="true">{portal.title} · unavailable</span>
          ))}
        </div>
      </div>
    </details>
  )
}
