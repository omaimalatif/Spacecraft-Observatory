import { useEffect, useState } from 'react'
import Starfield from './components/Starfield.jsx'
import Hero from './components/Hero.jsx'
import VisibilityExplorer from './components/VisibilityExplorer.jsx'
import PortalGrid from './components/PortalGrid.jsx'
import Footer from './components/Footer.jsx'
import GlobalAssetsDashboard from './components/GlobalAssetsDashboard.jsx'

export default function App() {
  const [route, setRoute] = useState(window.location.hash)

  useEffect(() => {
    const changeRoute = () => setRoute(window.location.hash)
    window.addEventListener('hashchange', changeRoute)
    return () => window.removeEventListener('hashchange', changeRoute)
  }, [])

  return (
    <>
      <div className="backdrop"></div>
      <Starfield />
      <div className="wrap">
        {route === '#/global-space-assets' ? <GlobalAssetsDashboard /> : <>
          <Hero />
          <VisibilityExplorer />
          <PortalGrid />
          <Footer />
        </>}
      </div>
    </>
  )
}
