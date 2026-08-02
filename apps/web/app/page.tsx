"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

type View = "command" | "stream" | "opportunities" | "health" | "settings";
type ApiState = "checking" | "ready" | "offline";

const navigation: { id: View; label: string; detail: string; icon: IconName }[] = [
  { id: "command", label: "Command center", detail: "Overview", icon: "grid" },
  { id: "stream", label: "Incident stream", detail: "Sarasota", icon: "pulse" },
  { id: "opportunities", label: "Opportunities", detail: "Review queue", icon: "spark" },
  { id: "health", label: "Data health", detail: "Source posture", icon: "shield" },
  { id: "settings", label: "Settings", detail: "Governance", icon: "sliders" },
];

type IconName = "grid" | "pulse" | "spark" | "shield" | "sliders" | "search" | "bell" | "arrow" | "refresh" | "lock" | "chevron" | "database" | "clock" | "filter";

function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
    pulse: <><path d="M3 12h4l2.2-6 4.3 12 2.2-6H21" /></>,
    spark: <><path d="m12 3 1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5L12 3Z" /><path d="m19 16 .7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7L19 16Z" /></>,
    shield: <><path d="M12 3 20 6v5c0 5-3.4 8.1-8 10-4.6-1.9-8-5-8-10V6l8-3Z" /><path d="m8.5 12 2.2 2.2 4.8-5" /></>,
    sliders: <><path d="M4 6h7M15 6h5M4 12h3M11 12h9M4 18h9M17 18h3" /><circle cx="13" cy="6" r="2" /><circle cx="9" cy="12" r="2" /><circle cx="15" cy="18" r="2" /></>,
    search: <><circle cx="10.8" cy="10.8" r="6.5" /><path d="m16 16 5 5" /></>,
    bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9ZM10 21h4" /></>,
    arrow: <><path d="M5 12h13" /><path d="m13 6 6 6-6 6" /></>,
    refresh: <><path d="M20 11a8 8 0 0 0-14.7-3L3 11" /><path d="M3 5v6h6" /><path d="M4 13a8 8 0 0 0 14.7 3L21 13" /><path d="M21 19v-6h-6" /></>,
    lock: <><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></>,
    chevron: <path d="m8 10 4 4 4-4" />,
    database: <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5" /><path d="M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7" /></>,
    clock: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7v5l3.5 2" /></>,
    filter: <path d="M4 6h16M7 12h10M10 18h4" />,
  };

  return (
    <svg aria-hidden="true" className="icon" height={size} viewBox="0 0 24 24" width={size} fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7">
      {paths[name]}
    </svg>
  );
}

function EmptyState({ title, body, action }: { title: string; body: string; action?: string }) {
  return (
    <div className="empty-state">
      <div className="empty-mark"><Icon name="database" size={20} /></div>
      <h3>{title}</h3>
      <p>{body}</p>
      {action ? <button className="button button-dark" type="button">{action}<Icon name="arrow" size={15} /></button> : null}
    </div>
  );
}

function SourcePill({ compact = false }: { compact?: boolean }) {
  return (
    <span className={`source-pill${compact ? " compact" : ""}`}>
      <span className="source-dot" />
      {compact ? "Sarasota / manual" : "Sarasota County · manual snapshots"}
    </span>
  );
}

function Metric({ label, value, note, tone = "neutral" }: { label: string; value: string; note: string; tone?: "neutral" | "green" | "amber" }) {
  return (
    <article className="metric-card">
      <p className="metric-label">{label}</p>
      <p className={`metric-value ${tone}`}>{value}</p>
      <p className="metric-note">{note}</p>
    </article>
  );
}

export default function Home() {
  const [activeView, setActiveView] = useState<View>("command");
  const [apiState, setApiState] = useState<ApiState>("checking");
  const [apiPhase, setApiPhase] = useState("local API");

  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

  const checkApi = useCallback(() => {
    setApiState("checking");
    fetch(`${apiBase}/healthz`, { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error("Health check failed");
        const payload = (await response.json()) as { phase?: string; live_polling_enabled?: boolean };
        setApiPhase(payload.phase ?? "local API");
        setApiState(payload.live_polling_enabled ? "offline" : "ready");
      })
      .catch(() => setApiState("offline"));
  }, [apiBase]);

  useEffect(() => {
    checkApi();
  }, [checkApi]);

  const activeLabel = useMemo(
    () => navigation.find((item) => item.id === activeView)?.label ?? "Command center",
    [activeView],
  );

  return (
    <div className="app-shell">
      <aside className="rail" aria-label="Primary navigation">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true"><span /><span /><span /></div>
          <div><p className="brand-name">Beyond</p><p className="brand-product">Fire Radar</p></div>
        </div>
        <div className="rail-rule" />
        <p className="rail-label">Workspace</p>
        <nav className="nav-list">
          {navigation.map((item) => (
            <button aria-label={`${item.label}: ${item.detail}`} className={`nav-item ${activeView === item.id ? "active" : ""}`} key={item.id} onClick={() => setActiveView(item.id)} type="button" aria-current={activeView === item.id ? "page" : undefined}>
              <Icon name={item.icon} />
              <span><strong>{item.label}</strong><small>{item.detail}</small></span>
            </button>
          ))}
        </nav>
        <div className="rail-bottom">
          <div className="rail-status"><span className="status-dot status-dot-amber" /><span><strong>Research environment</strong><small>Human review required</small></span></div>
          <div className="user-chip"><span className="avatar">SA</span><span><strong>Shalev</strong><small>Administrator</small></span><Icon name="chevron" size={15} /></div>
        </div>
      </aside>

      <main className="content">
        <header className="topbar">
          <div className="mobile-brand"><div className="brand-mark" aria-hidden="true"><span /><span /><span /></div><strong>Beyond Fire Radar</strong></div>
          <div className="crumbs"><span>Workspace</span><span className="crumb-divider">/</span><strong>{activeLabel}</strong></div>
          <div className="top-actions">
            <button className="icon-button" type="button" aria-label="Search"><Icon name="search" /></button>
            <button className="icon-button notification" type="button" aria-label="Notifications"><Icon name="bell" /><span /></button>
            <div className="top-divider" />
            <SourcePill compact />
          </div>
        </header>

        <div className="workspace">
          <div className="workspace-head">
            <div>
              <p className="eyebrow">FIELD OPERATIONS <span>·</span> SARASOTA COUNTY</p>
              <h1>{activeView === "command" ? "Review the signal, keep the uncertainty." : activeLabel}</h1>
              <p className="workspace-lede">{activeView === "command" ? "A quiet command center for evidence-led property-loss research. Every record stays traceable to the source that supplied it." : viewDescription(activeView)}</p>
            </div>
            <div className="head-actions"><SourcePill /><button className="button button-light" type="button"><Icon name="filter" size={15} /> Filters <span className="filter-count">0</span></button></div>
          </div>

          <div className="safety-banner" role="status">
            <div className="banner-icon"><Icon name="shield" size={17} /></div>
            <div><strong>Research environment</strong><span>Live Sarasota polling is disabled. Manual snapshots only.</span></div>
            <span className="banner-status"><span className="status-dot status-dot-amber" /> Protected</span>
          </div>

          {activeView === "command" ? <CommandView apiState={apiState} apiPhase={apiPhase} onRetry={checkApi} /> : null}
          {activeView === "stream" ? <StreamView /> : null}
          {activeView === "opportunities" ? <OpportunityView /> : null}
          {activeView === "health" ? <HealthView apiState={apiState} apiPhase={apiPhase} onRetry={checkApi} /> : null}
          {activeView === "settings" ? <SettingsView /> : null}
        </div>

        <footer className="content-footer"><span>Beyond Adjusting · Internal research only</span><span>Source provenance is required for every decision</span></footer>
      </main>
    </div>
  );
}

function viewDescription(view: View) {
  const descriptions: Record<View, string> = {
    command: "A quiet command center for evidence-led property-loss research.",
    stream: "Source-preserving incident updates from approved Sarasota snapshots.",
    opportunities: "Provisional research ranking, never an empirical probability.",
    health: "Freshness, provenance, and integration posture at a glance.",
    settings: "Governance controls for a deliberately constrained workspace.",
  };
  return descriptions[view];
}

function CommandView({ apiState, apiPhase, onRetry }: { apiState: ApiState; apiPhase: string; onRetry: () => void }) {
  const [workbenchTab, setWorkbenchTab] = useState<"incident" | "property" | "evidence">("incident");
  const workbenchTabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const workbenchTabs: Array<{ id: "incident" | "property" | "evidence"; label: string }> = [
    { id: "incident", label: "Incident" },
    { id: "property", label: "Property" },
    { id: "evidence", label: "Evidence" },
  ];
  const handleWorkbenchKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const direction = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    const targetIndex = direction ? (index + direction + workbenchTabs.length) % workbenchTabs.length : event.key === "Home" ? 0 : event.key === "End" ? workbenchTabs.length - 1 : -1;
    if (targetIndex >= 0) {
      event.preventDefault();
      setWorkbenchTab(workbenchTabs[targetIndex].id);
      workbenchTabRefs.current[targetIndex]?.focus();
    }
  };
  const workbenchCopy = {
    incident: { title: "Select an incident to inspect", body: "Raw source rows, linkage explanations, contradictions, and reviewer decisions will stay together here." },
    property: { title: "Select a property candidate to inspect", body: "Property evidence remains unavailable until a governed incident-to-property workflow supplies a candidate." },
    evidence: { title: "Select evidence to inspect", body: "Source provenance, freshness, and contradictory evidence will be shown without collapsing the original record." },
  }[workbenchTab];
  return <>
    <section className="metric-grid" aria-label="Workspace metrics">
      <Metric label="Review queue" value="Not loaded" note="Dashboard record feed not connected" />
      <Metric label="Needs attention" value="Not loaded" note="Dashboard record feed not connected" tone="amber" />
      <Metric label="Source freshness" value="Unknown" note="Manual snapshot timing not loaded" tone="amber" />
      <Metric label="Data posture" value={apiState === "ready" ? "Ready" : apiState === "checking" ? "Checking" : "Offline"} note={apiState === "ready" ? apiPhase : "Safe empty state"} tone={apiState === "offline" ? "amber" : "neutral"} />
    </section>
    {apiState === "offline" ? <div className="inline-error" role="alert"><Icon name="pulse" size={17} /><span><strong>API is unavailable.</strong> The interface is showing a safe empty state; no records are being implied.</span><button onClick={onRetry} type="button">Retry</button></div> : null}
    <div className="dashboard-grid">
      <section className="panel panel-queue" aria-labelledby="queue-title">
        <div className="panel-heading"><div><p className="section-kicker">TODAY</p><h2 id="queue-title">Review queue</h2></div><button className="text-button" type="button">View all <Icon name="arrow" size={15} /></button></div>
        <EmptyState title="Review queue not connected" body="No queue state is being implied. When a governed dashboard read workflow is connected, incidents with unresolved evidence will appear here for review." />
      </section>
      <aside className="right-stack">
        <section className="panel source-panel" aria-labelledby="source-title">
          <div className="panel-heading"><div><p className="section-kicker">SOURCE POSTURE</p><h2 id="source-title">Sarasota dispatch</h2></div><span className="mini-tag">Manual</span></div>
          <div className="source-graphic"><div className="source-orbit orbit-one" /><div className="source-orbit orbit-two" /><div className="source-core"><Icon name="database" size={19} /></div></div>
          <div className="source-row"><span>Collection mode</span><strong>Manual snapshots</strong></div><div className="source-row"><span>Live polling</span><strong className="amber-text">Disabled</strong></div><div className="source-row"><span>Approval state</span><strong>Not asserted</strong></div>
          <p className="panel-note">The source boundary is visible by design. Manual availability does not imply legal approval.</p>
        </section>
        <section className="panel principles-panel" aria-labelledby="principles-title"><p className="section-kicker">REVIEW PRINCIPLES</p><h2 id="principles-title">Evidence before escalation.</h2><ul className="principles"><li><span>01</span>Keep raw source rows inspectable.</li><li><span>02</span>Abstain when property evidence is weak.</li><li><span>03</span>Record every human decision.</li></ul></section>
      </aside>
    </div>
    <div className="operations-grid">
      <section className="panel map-panel" aria-labelledby="map-title">
        <div className="panel-heading"><div><p className="section-kicker">GEOSPATIAL CONTEXT</p><h2 id="map-title">Incident map</h2></div><span className="soft-label">No live feed</span></div>
        <div className="map-empty">
          <div className="map-grid-lines" aria-hidden="true"><span /><span /><span /><span /></div>
          <div className="map-empty-copy"><div className="empty-mark"><Icon name="pulse" size={20} /></div><h3>No geospatial incidents to plot</h3><p>Map context will remain empty until a source-preserving Sarasota snapshot creates canonical incidents.</p></div>
        </div>
      </section>
      <section className="panel workbench-panel" aria-labelledby="workbench-title">
        <div className="panel-heading"><div><p className="section-kicker">EVIDENCE REVIEW</p><h2 id="workbench-title">Workbench</h2></div><span className="mini-tag">No record selected</span></div>
        <div className="workbench-tabs" role="tablist" aria-label="Workbench context">{workbenchTabs.map((tab, index) => <button aria-controls="workbench-panel" aria-selected={workbenchTab === tab.id} className={workbenchTab === tab.id ? "active" : ""} id={`workbench-tab-${tab.id}`} key={tab.id} onClick={() => setWorkbenchTab(tab.id)} onKeyDown={(event) => handleWorkbenchKeyDown(event, index)} ref={(element) => { workbenchTabRefs.current[index] = element; }} role="tab" tabIndex={workbenchTab === tab.id ? 0 : -1} type="button">{tab.label}</button>)}</div>
        <div id="workbench-panel" role="tabpanel" aria-labelledby={`workbench-tab-${workbenchTab}`}><EmptyState title={workbenchCopy.title} body={workbenchCopy.body} /></div>
      </section>
    </div>
      <section className="panel property-panel" aria-labelledby="property-title">
      <div className="panel-heading"><div><p className="section-kicker">PROPERTY INTELLIGENCE</p><h2 id="property-title">Property context</h2></div><span className="soft-label">Not loaded</span></div>
      <div className="property-empty"><div className="property-icon"><Icon name="lock" size={19} /></div><div><h3>Property resolution is not available in this view</h3><p>No address-to-parcel result is being implied. Property evidence will appear only after the approved ingestion and human-review steps provide it.</p></div><span className="property-boundary">Phase 4 boundary</span></div>
    </section>
  </>;
}

function StreamView() {
  return <section className="panel full-panel" aria-labelledby="stream-title"><div className="panel-heading"><div><p className="section-kicker">SOURCE-PRESERVING VIEW</p><h2 id="stream-title">Incident stream</h2></div><div className="view-tools"><span className="soft-label"><Icon name="clock" size={14} /> Latest first</span><button className="button button-light" type="button"><Icon name="filter" size={15} /> Filter</button></div></div><div className="stream-empty"><div className="empty-line" /><EmptyState title="Incident feed not connected" body="Canonical Sarasota incidents will appear after a governed read workflow is connected to an approved manual or fixture snapshot. Live polling is not active." /></div></section>;
}

function OpportunityView() {
  return <><div className="notice-card"><div className="notice-mark"><Icon name="spark" size={18} /></div><div><strong>Provisional research ranking</strong><p>Scores summarize available evidence. They are not probabilities, damage findings, coverage opinions, or contact recommendations.</p></div><span className="version-tag">v1</span></div><section className="panel full-panel" aria-labelledby="opportunity-title"><div className="panel-heading"><div><p className="section-kicker">HUMAN REVIEW ONLY</p><h2 id="opportunity-title">Opportunity pipeline</h2></div><span className="soft-label">Not loaded</span></div><EmptyState title="Opportunity feed not connected" body="The pipeline will show provisional research rankings only after a governed read workflow supplies resolved evidence. No opportunity count is being implied." /></section></>;
}

function HealthView({ apiState, apiPhase, onRetry }: { apiState: ApiState; apiPhase: string; onRetry: () => void }) {
  return <div className="health-grid"><section className="panel full-panel" aria-labelledby="health-title"><div className="panel-heading"><div><p className="section-kicker">INTEGRATION POSTURE</p><h2 id="health-title">Data health</h2></div><button className="button button-light" onClick={onRetry} type="button"><Icon name="refresh" size={15} /> Refresh</button></div><div className="health-list"><HealthRow label="Sarasota dispatch provider" status="Manual only" detail="Live polling disabled" tone="amber" /><HealthRow label="Local API" status={apiState === "ready" ? "Reachable" : apiState === "checking" ? "Checking" : "Unavailable"} detail={apiState === "ready" ? apiPhase : "Safe empty state"} tone={apiState === "ready" ? "green" : "amber"} /><HealthRow label="PostgreSQL / PostGIS" status="Not connected" detail="External integration gate" tone="neutral" /><HealthRow label="Redis" status="Not connected" detail="External integration gate" tone="neutral" /></div></section><section className="panel health-note-panel"><div className="large-lock"><Icon name="lock" size={21} /></div><p className="section-kicker">GOVERNANCE</p><h2>Boundaries are part of the product.</h2><p>Every source, model output, and reviewer decision should make its provenance and uncertainty visible.</p></section></div>;
}

function HealthRow({ label, status, detail, tone }: { label: string; status: string; detail: string; tone: "green" | "amber" | "neutral" }) {
  return <div className="health-row"><span className={`health-dot ${tone}`} /><div><strong>{label}</strong><small>{detail}</small></div><span className={`health-status ${tone}`}>{status}</span></div>;
}

function SettingsView() {
  return <div className="settings-grid"><section className="panel full-panel" aria-labelledby="settings-title"><div className="panel-heading"><div><p className="section-kicker">CONTROLLED CONFIGURATION</p><h2 id="settings-title">Settings</h2></div><span className="mini-tag">Admin</span></div><div className="settings-list"><SettingRow label="Live Sarasota polling" detail="External approval and feature flag required" value="Disabled" /><SettingRow label="Automatic consumer outreach" detail="Not implemented by policy" value="Unavailable" /><SettingRow label="Probability display" detail="Only calibrated real-world models may use probability language" value="Off" /><SettingRow label="Human review" detail="Required for unresolved or contradictory evidence" value="Required" /></div></section><section className="panel settings-side"><div className="avatar large-avatar">SA</div><p className="section-kicker">CURRENT SESSION</p><h2>Administrator</h2><p className="panel-note">Role checks happen in the API. The browser is not a trusted authorization boundary.</p><button className="button button-light" type="button"><Icon name="lock" size={15} /> Review access policy</button></section></div>;
}

function SettingRow({ label, detail, value }: { label: string; detail: string; value: string }) {
  return <div className="setting-row"><div><strong>{label}</strong><small>{detail}</small></div><span className="setting-value">{value}</span></div>;
}
