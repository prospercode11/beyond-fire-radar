const foundationItems = [
  ["Auth + roles", "Ready"],
  ["Audit trail", "Ready"],
  ["Provider registry", "Ready"],
  ["Live dispatch polling", "Disabled"],
];

export default function Home() {
  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">BEYOND ADJUSTING / INTERNAL</p>
          <h1>Beyond Fire Radar</h1>
        </div>
        <span className="phase">Phase 1 · Foundation</span>
      </header>

      <section className="hero" aria-labelledby="hero-title">
        <p className="eyebrow">CONTROLLED BUILD</p>
        <h2 id="hero-title">A governed starting point for property-loss intelligence.</h2>
        <p className="lede">
          The foundation is online. Future phases will add authorized source ingestion and human-reviewed
          incident intelligence; no consumer outreach or unvalidated probability claims are enabled here.
        </p>
      </section>

      <section className="status-grid" aria-label="Foundation status">
        {foundationItems.map(([label, status]) => (
          <article className="status-card" key={label}>
            <span className={status === "Disabled" ? "status-dot muted" : "status-dot"} aria-hidden="true" />
            <div>
              <p className="card-label">{label}</p>
              <p className="card-status">{status}</p>
            </div>
          </article>
        ))}
      </section>

      <footer className="footer">
        <span>Evidence before escalation.</span>
        <span>Research only · Human review required.</span>
      </footer>
    </main>
  );
}
