export default function PortalCard({ color, title, desc, href = '#' }) {
  const card = (
    <article className={`portal-card glass${href === '#' ? ' is-unavailable' : ''}`} style={{ '--pc': color }}>
      <div>
        <h3>{title}</h3>
        <p className="desc">{desc}</p>
      </div>
      <span className="portal-action">
        {href === '#' ? 'Portal unavailable' : <>Open portal <strong aria-hidden="true">→</strong></>}
      </span>
    </article>
  )

  return href === '#' ? card : <a className="portal-card-link" href={href}>{card}</a>
}
