import { useEffect, useState } from 'react'
import Starfield from './components/Starfield.jsx'
import Hero from './components/Hero.jsx'
import VisibilityExplorer from './components/VisibilityExplorer.jsx'
import PortalGrid from './components/PortalGrid.jsx'
import Footer from './components/Footer.jsx'
import GlobalAssetsDashboard from './components/GlobalAssetsDashboard.jsx'
import NavigationDashboard from './components/NavigationDashboard.jsx'
import EarthObservation from './components/EarthObservation.jsx'
import SpaceScience from './components/SpaceScience.jsx'

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
        {route === '#/global-space-assets' ? <GlobalAssetsDashboard /> :
         route === '#/navigation-systems' ? <NavigationDashboard /> :
         route === '#/earth-observation' ? <EarthObservation /> :
         route === '#/space-science' ? <SpaceScience /> : <>
          <Hero />
          <PortalGrid />
          <VisibilityExplorer />
          <Footer />
        </>}
      </div>
    </>
  )
}
