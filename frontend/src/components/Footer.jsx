const PARTNER_LOGOS = [
  { alt: 'Government of Pakistan', src: '/partners/govt-of-pakistan.png', href: 'https://www.pakistan.gov.pk' },
  { alt: 'Higher Education Commission', src: '/partners/hec.png', href: 'https://www.hec.gov.pk' },
  { alt: 'NCGSA', src: '/ncgsa-logo.png', href: 'https://ncgsa.org.pk' },
  { alt: 'Institute of Space Technology', src: '/partners/ist.png', href: 'https://ist.edu.pk' },
  { alt: 'GNSS Research Lab, IST Islamabad', src: '/partners/gnss-research-lab.png', href: 'https://ncgsa.org.pk' },
]

const EXPLORE_LINKS = [
  { label: 'Global Assets', href: '#portals' },
  { label: 'Visibility', href: '#visibility' },
  { label: 'Missions', href: '#portals' },
  { label: 'Sources', href: '#footer-sources' },
]

function IconLink({ href, icon, label }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="icon-link">
      <span className="icon-link-badge">{icon}</span>
      <span>{label}</span>
    </a>
  )
}

const LinkedInIcon = (
  <svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor">
    <path d="M20.45 20.45h-3.56v-5.57c0-1.33-.02-3.04-1.85-3.04-1.86 0-2.14 1.45-2.14 2.94v5.67H9.34V9h3.41v1.56h.05c.48-.9 1.64-1.85 3.38-1.85 3.6 0 4.27 2.37 4.27 5.46v6.28zM5.34 7.43a2.07 2.07 0 1 1 0-4.13 2.07 2.07 0 0 1 0 4.13zM7.12 20.45H3.56V9h3.56v11.45z"/>
  </svg>
)

const WebsiteIcon = (
  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.8">
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18M12 3c2.5 2.6 3.8 5.7 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.7-3.8-9S9.5 5.6 12 3z" />
  </svg>
)

const PinIcon = (
  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.8">
    <path d="M12 21s-7-6.1-7-11.5A7 7 0 0 1 19 9.5C19 14.9 12 21 12 21z" />
    <circle cx="12" cy="9.5" r="2.4" />
  </svg>
)

const ArrowIcon = (
  <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M9 5l7 7-7 7" />
  </svg>
)

export default function Footer() {
  return (
    <footer id="footer-sources">
      <div className="footer-partners">
        {PARTNER_LOGOS.map((p) => (
          <a
            className="partner-logo"
            href={p.href}
            target="_blank"
            rel="noopener noreferrer"
            key={p.alt}
            title={p.alt}
            aria-label={p.alt}
          >
            <img src={p.src} alt={p.alt} />
          </a>
        ))}
      </div>

      <div className="footer-grid">
        <div className="footer-col">
          <span className="footer-label">GNSS Research Lab</span>
          <h3>NCGSA Spacecraft Observatory</h3>
          <p>Real-time monitoring of humanity's presence in orbit.</p>
          <p>Operational dashboard and research data hub.</p>

          <div className="footer-divider" />

          <span className="footer-label">GNSS Contact</span>
          <p className="contact-line">
            <span className="contact-icon">{PinIcon}</span>
            1, Islamabad Highway, Islamabad 44000
          </p>
          <div className="footer-social">
            <IconLink href="https://pk.linkedin.com/company/ncgsa" icon={LinkedInIcon} label="LinkedIn" />
            <IconLink href="https://ncgsa.org.pk" icon={WebsiteIcon} label="Website" />
          </div>
        </div>

        <div className="footer-col">
          <span className="footer-label">NCGSA</span>
          <h3>National Center of GIS and Space Applications</h3>
          <p>Institute of Space Technology, Islamabad, Pakistan</p>
          <div className="footer-social">
            <IconLink href="https://pk.linkedin.com/school/ist-islamabad/" icon={LinkedInIcon} label="LinkedIn" />
            <IconLink href="https://ist.edu.pk" icon={WebsiteIcon} label="Website" />
          </div>
        </div>

        <div className="footer-col">
          <span className="footer-label">Explore</span>
          <div className="explore-grid">
            {EXPLORE_LINKS.map((l) => (
              <a href={l.href} className="explore-link" key={l.label}>
                {l.label} <span className="explore-arrow">{ArrowIcon}</span>
              </a>
            ))}
          </div>
        </div>
      </div>

      <p className="fine">
        ORBITAL is the NCGSA Spacecraft Observatory frontend. Satellite counts, orbit
        classifications and visibility calculations are computed by the Python/FastAPI
        backend from CelesTrak, NASA and Open Notify data.
      </p>
    </footer>
  )
}
