export default function PortalCard({ num, color, icon, title, desc, tags, metrics, href = '#' }) {
  return (
    <a className="portal-card glass" style={{ '--pc': color }} href={href}>
      <div className="portal-top">
        <span className="portal-num">{num}</span>
        <div className="portal-icon">{icon}</div>
      </div>
      <div>
        <h3>{title}</h3>
        <p className="desc">{desc}</p>
        {metrics && (
          <div className="portal-metrics">
            {metrics.map((m) => (
              <div key={m.label}><b>{m.value}</b><span>{m.label}</span></div>
            ))}
          </div>
        )}
        <div className="portal-tags">
          {tags.map((t) => <span key={t}>{t}</span>)}
        </div>
      </div>
    </a>
  )
}
