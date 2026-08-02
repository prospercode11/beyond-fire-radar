"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";

type View = "command" | "stream" | "opportunities" | "workflow" | "analytics" | "learning" | "health" | "settings";
type IconName = "grid" | "pulse" | "spark" | "shield" | "sliders" | "search" | "bell" | "arrow" | "refresh" | "lock" | "chevron" | "database" | "clock" | "filter" | "upload" | "logout" | "check" | "warning";
type JsonMap = Record<string, unknown>;

type Provider = {
  id: string;
  name: string;
  source_authority: string;
  geographic_coverage: string;
  data_type: string;
  authorized_use_status: string;
  enabled: boolean;
  schema_version: string;
  parser_version: string;
  limitations: string;
};

type ProviderHealth = {
  provider_id: string;
  last_successful_retrieval: string | null;
  last_changed_retrieval: string | null;
  last_snapshot_hash: string | null;
  last_retrieval_status: string | null;
  failure_count: number;
  circuit_state: string;
  schema_drift_detected: boolean;
  schema_alert_count: number;
  known_status_note: string;
};

type ImportJob = {
  import_job_id: string;
  retrieval_id: string;
  provider_id: string;
  status: string;
  format: string;
  parser_version: string;
  schema_version: string;
  content_hash: string;
  normalized_record_count: number;
  rejected_record_count: number;
  schema_alert_count: number;
  replayed: boolean;
  error: string | null;
  acquisition_mode: string;
  authorization_basis: string | null;
  created_at: string;
};

type IncidentSummary = {
  id: string;
  provider_id: string;
  state: string;
  classification_family: string;
  classification_version: string;
  classification_confidence: number;
  confidence_band: string;
  review_band: string;
  first_event_time: string | null;
  last_event_time: string | null;
  canonical_location: string | null;
  contradiction_count: number;
  review_signal_status: string;
  review_signal_issued_at: string | null;
  review_signal_revoked_at: string | null;
  review_signal_revocation_reason: string | null;
  observation_count: number;
  is_active: boolean;
  merged_into_id: string | null;
  source_acquisition_modes: string[];
};

type IncidentDetail = IncidentSummary & {
  canonical_event_type: string | null;
  canonical_grid: string | null;
  canonical_agency: string | null;
  canonical_station: string | null;
  classification_explanation: JsonMap;
  current_explanation: JsonMap;
  source_acquisition_modes: string[];
  source_retrieval_ids: string[];
  observations: Observation[];
  source_row_ids: string[];
  relationship_history: JsonMap[];
  timeline: JsonMap[];
  evidence: JsonMap[];
  match_decisions: JsonMap[];
  aliases: JsonMap[];
};

type Observation = {
  id: string;
  raw_dispatch_row_id: string;
  source_record_id: string;
  source_event_id: string | null;
  source_case_number: string | null;
  agency: string | null;
  station: string | null;
  event_time: string | null;
  retrieved_at: string;
  original_event_type: string;
  normalized_event_family: string;
  original_location: string;
  location_precision: string | null;
  latitude: number | null;
  longitude: number | null;
  grid: string | null;
  parser_confidence: number;
  parser_version: string;
  taxonomy_version: string;
  raw_payload_reference: string;
};

type Parcel = {
  id: string;
  provider_id: string;
  parcel_id: string;
  is_active: boolean;
  source_version: string;
  effective_at: string | null;
  situs_original: string;
  normalized_address: string;
  address_precision: string;
  municipality: string | null;
  postal_code: string | null;
  property_use_code: string | null;
  property_use_category: string | null;
  owner_name: string | null;
  mailing_address: string | null;
  year_built: number | null;
  building_area: number | null;
  number_of_buildings: number | null;
  number_of_units: number | null;
  stories: number | null;
  latitude: number | null;
  longitude: number | null;
  master_parcel_id: string | null;
  data_quality: JsonMap;
  provenance: JsonMap;
};

type PropertyCandidate = {
  id: string;
  incident_id: string;
  parcel_id: string;
  rank: number;
  match_score: number;
  score_margin: number | null;
  classification: string;
  recommendation_status: string;
  is_abstained: boolean;
  supporting_evidence: JsonMap[];
  contradictory_evidence: JsonMap[];
  features: JsonMap;
  explanation: JsonMap;
  property_data_quality: JsonMap;
  parcel: Parcel;
};

type PropertyMatch = {
  id: string;
  incident_id: string;
  property_provider_id: string;
  property_import_id: string | null;
  status: string;
  matcher_version: string;
  address_normalization_version: string;
  candidate_count: number;
  abstention_reason: string | null;
  source_observation_ids: string[];
  created_at: string;
  completed_at: string | null;
  candidates: PropertyCandidate[];
  current_human_decision: JsonMap | null;
};

type ScoreFeature = {
  id: string;
  feature_name: string;
  value: number | null;
  status: string;
  contribution: number | null;
  evidence: JsonMap;
  source_observation_ids: string[];
  available_at: string | null;
  feature_version: string;
  explanation: string;
};

type Opportunity = {
  id: string;
  incident_id: string;
  property_match_run_id: string | null;
  property_provider_id: string | null;
  scoring_version: string;
  previous_score_run_id: string | null;
  as_of: string;
  status: string;
  provisional_score: number | null;
  evidence_tier: string;
  alert_eligibility: boolean;
  abstention_reason: string | null;
  hard_gate_status: string;
  explanation: JsonMap;
  source_observation_ids: string[];
  available_at: string | null;
  created_at: string;
  completed_at: string | null;
  is_current: boolean;
  features: ScoreFeature[];
  human_override: JsonMap | null;
};

type WorkflowAlert = {
  id: string;
  incident_id: string;
  score_run_id: string;
  dedupe_key: string;
  alert_type: string;
  severity: string;
  status: string;
  title: string;
  summary: string;
  evidence_snapshot: JsonMap;
  suppression_reason: string | null;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  snoozed_until: string | null;
  revoked_by: string | null;
  revoked_at: string | null;
  escalated_by: string | null;
  escalated_at: string | null;
  created_at: string;
  updated_at: string;
};

type Assignment = {
  id: string | null;
  incident_id: string;
  assignee_user_id: string | null;
  role: string | null;
  reason: string | null;
  actor_user_id: string | null;
  ended_at: string | null;
  created_at: string | null;
};

type WorkflowNote = {
  id: string;
  incident_id: string;
  body: string;
  note_type: string;
  author_user_id: string;
  created_at: string;
};

type AnalyticsMetric = {
  id: string;
  manifest_id: string;
  metric_name: string;
  metric_version: string;
  numerator: number | null;
  denominator: number;
  value: number | null;
  status: string;
  warning: string | null;
  details: JsonMap;
  created_at: string;
};

type AnalyticsReport = {
  manifest: {
    id: string;
    manifest_type: string;
    manifest_version: string;
    as_of: string;
    filters: JsonMap;
    incident_ids: string[];
    score_run_ids: string[];
    label_ids: string[];
    outcome_event_ids: string[];
    source_acquisition_modes: string[];
    source_retrieval_ids: string[];
    source_property_import_ids: string[];
    source_provider_ids: string[];
    source_authorization_bases: string[];
    source_snapshot_hashes: string[];
    source_provenance: JsonMap;
    claim_status: string;
    created_by: string;
    created_at: string;
  };
  metrics: AnalyticsMetric[];
};

type LearningPolicy = {
  mode: string;
  model_release_id: string | null;
  learned_model_active: boolean;
  reason: string;
  probability_display: boolean;
};

type LearningModel = {
  id: string;
  model_version: string;
  algorithm: string;
  status: string;
  feature_set_id: string;
  label_set_id: string;
  dataset_snapshot_id: string;
  approval_required: boolean;
  approved_by: string | null;
  inactive_reason: string | null;
  evaluation: JsonMap;
  training_report: JsonMap;
  model_card: JsonMap;
  created_at: string;
};

const navigation: { id: View; label: string; detail: string; icon: IconName }[] = [
  { id: "command", label: "Command center", detail: "Overview", icon: "grid" },
  { id: "stream", label: "Incident stream", detail: "Sarasota", icon: "pulse" },
  { id: "opportunities", label: "Opportunities", detail: "Review queue", icon: "spark" },
  { id: "workflow", label: "Workflow", detail: "Internal alerts", icon: "bell" },
  { id: "analytics", label: "Outcomes", detail: "Analytics", icon: "database" },
  { id: "learning", label: "Model lab", detail: "Governed learning", icon: "database" },
  { id: "health", label: "Data health", detail: "Source posture", icon: "shield" },
  { id: "settings", label: "Settings", detail: "Governance", icon: "sliders" },
];

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

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
    upload: <><path d="M12 16V4" /><path d="m7 9 5-5 5 5" /><path d="M5 20h14" /></>,
    logout: <><path d="M10 5H5v14h5" /><path d="m14 8 4 4-4 4" /><path d="M18 12H9" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    warning: <><path d="M12 3 2.5 20h19L12 3Z" /><path d="M12 9v5M12 17h.01" /></>,
  };
  return <svg aria-hidden="true" className="icon" height={size} viewBox="0 0 24 24" width={size} fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7">{paths[name]}</svg>;
}

function formatDate(value: string | null | undefined, withTime = false) {
  if (!value) return "Unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", withTime ? { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" } : { month: "short", day: "numeric", year: "numeric" }).format(date);
}

function label(value: string | null | undefined) {
  return (value ?? "unknown").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return <div className="empty-state"><div className="empty-mark"><Icon name="database" size={20} /></div><h3>{title}</h3><p>{body}</p></div>;
}

function sourceModeLabel(modes: string[]) {
  const unique = [...new Set(modes)];
  if (unique.includes("synthetic_fixture") && unique.includes("manual_snapshot")) return "Sarasota · mixed manual/test";
  if (unique.includes("synthetic_fixture")) return "Sarasota · test fixture";
  if (unique.includes("manual_snapshot")) return "Sarasota · manual snapshot";
  if (unique.includes("live_poll")) return "Sarasota · live-collected (disabled)";
  return "Sarasota · source mode unknown";
}

function SourcePill({ compact = false, modes = [] }: { compact?: boolean; modes?: string[] }) {
  const text = modes.length ? sourceModeLabel(modes) : "Sarasota · manual/test source";
  return <span className={`source-pill${compact ? " compact" : ""}`}><span className="source-dot" />{text}</span>;
}

function Metric({ label: title, value, note, tone = "neutral" }: { label: string; value: string; note: string; tone?: "neutral" | "green" | "amber" }) {
  return <article className="metric-card"><p className="metric-label">{title}</p><p className={`metric-value ${tone}`}>{value}</p><p className="metric-note">{note}</p></article>;
}

async function apiRequest<T>(path: string, token: string | null, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let response: Response;
  try { response = await fetch(`${apiBase}${path}`, { ...init, headers, cache: "no-store" }); }
  catch (caught) { throw new Error(`${path}: ${caught instanceof Error ? caught.message : "network request failed"}`); }
  const text = await response.text();
  let body: unknown = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = text; }
  if (!response.ok) {
    const detail = typeof body === "object" && body !== null && "detail" in body ? String((body as { detail: unknown }).detail) : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return body as T;
}

function AuthScreen({ onAuthenticated }: { onAuthenticated: (token: string) => void }) {
  const [mode, setMode] = useState<"login" | "bootstrap">("login");
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("");
  const [bootstrapAvailable, setBootstrapAvailable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { apiRequest<{ available: boolean }>("/api/v1/auth/bootstrap/status", null).then((result) => setBootstrapAvailable(result.available)).catch(() => undefined); }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError(null);
    try {
      const result = await apiRequest<{ access_token: string }>(mode === "bootstrap" ? "/api/v1/auth/bootstrap" : "/api/v1/auth/login", null, { method: "POST", body: JSON.stringify({ email, password }) });
      sessionStorage.setItem("beyond-fire-radar-token", result.access_token);
      onAuthenticated(result.access_token);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Authentication failed"); }
    finally { setBusy(false); }
  }

  return <main className="auth-screen"><section className="auth-card"><div className="auth-brand"><div className="brand-mark" aria-hidden="true"><span /><span /><span /></div><div><p className="brand-name">Beyond</p><p className="brand-product">Fire Radar</p></div></div><p className="eyebrow">INTERNAL RESEARCH ENVIRONMENT</p><h1>Evidence before escalation.</h1><p className="auth-lede">Sign in to inspect authorized Sarasota records, preserve source context, and make human review decisions.</p><form onSubmit={submit}><label>Email<input autoComplete="username" onChange={(event) => setEmail(event.target.value)} required type="email" value={email} /></label><label>Password<input autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={12} onChange={(event) => setPassword(event.target.value)} required type="password" value={password} /></label>{error ? <div className="form-error" role="alert"><Icon name="warning" size={16} />{error}</div> : null}<button className="button button-dark auth-submit" disabled={busy} type="submit">{busy ? "Working…" : mode === "login" ? "Sign in" : "Create development administrator"}<Icon name="arrow" size={15} /></button></form>{bootstrapAvailable ? <button className="auth-mode" onClick={() => setMode(mode === "login" ? "bootstrap" : "login")} type="button">{mode === "login" ? "First run? Create the configured development administrator" : "Back to sign in"}</button> : null}<p className="auth-boundary"><Icon name="lock" size={14} />The API enforces authentication and role permissions. Live collection and consumer outreach are disabled.</p></section></main>;
}

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [sessionReady, setSessionReady] = useState(false);
  useEffect(() => { setToken(sessionStorage.getItem("beyond-fire-radar-token")); setSessionReady(true); }, []);
  function authenticated(nextToken: string) { setToken(nextToken); }
  function logout() { sessionStorage.removeItem("beyond-fire-radar-token"); setToken(null); }
  if (!sessionReady) return <main className="auth-screen"><div className="loading-card">Connecting to the internal workspace…</div></main>;
  if (!token) return <AuthScreen onAuthenticated={authenticated} />;
  return <Workspace token={token} onLogout={logout} />;
}

function Workspace({ token, onLogout }: { token: string; onLogout: () => void }) {
  const [activeView, setActiveView] = useState<View>("command");
  const [user, setUser] = useState<{ id: string; display_name: string; email: string; roles: string[] } | null>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [health, setHealth] = useState<Record<string, ProviderHealth>>({});
  const [retrievals, setRetrievals] = useState<ImportJob[]>([]);
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<IncidentDetail | null>(null);
  const [propertyMatch, setPropertyMatch] = useState<PropertyMatch | null>(null);
  const [score, setScore] = useState<Opportunity | null>(null);
  const [alerts, setAlerts] = useState<WorkflowAlert[]>([]);
  const [assignment, setAssignment] = useState<Assignment | null>(null);
  const [notes, setNotes] = useState<WorkflowNote[]>([]);
  const [analyticsReport, setAnalyticsReport] = useState<AnalyticsReport | null>(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [learningPolicy, setLearningPolicy] = useState<LearningPolicy | null>(null);
  const [learningModels, setLearningModels] = useState<LearningModel[]>([]);
  const [learningLoading, setLearningLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const request = useCallback(<T,>(path: string, init?: RequestInit) => apiRequest<T>(path, token, init), [token]);
  const loadWorkspace = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [me, providerResult, incidentResult, opportunityResult] = await Promise.all([
        request<{ id: string; display_name: string; email: string; roles: string[] }>("/api/v1/auth/me"),
        request<{ providers: Provider[] }>("/api/v1/providers"),
        request<IncidentSummary[]>("/api/v1/incidents?limit=500"),
        request<Opportunity[]>("/api/v1/opportunities?limit=500"),
      ]);
      setUser(me); setProviders(providerResult.providers); setIncidents(incidentResult); setOpportunities(opportunityResult);
      setAlerts(await request<WorkflowAlert[]>("/api/v1/workflow/alerts"));
      const providerHealthEntries = await Promise.all(providerResult.providers.map(async (provider) => { try { return [provider.id, await request<ProviderHealth>(`/api/v1/providers/${encodeURIComponent(provider.id)}/health`)] as const; } catch { return [provider.id, null] as const; } }));
      const retrievalEntries = await Promise.all(providerResult.providers.map(async (provider) => { try { return await request<ImportJob[]>(`/api/v1/providers/${encodeURIComponent(provider.id)}/retrievals`); } catch { return []; } }));
      setHealth(Object.fromEntries(providerHealthEntries.filter((entry): entry is readonly [string, ProviderHealth] => entry[1] !== null)));
      setRetrievals(retrievalEntries.flat());
    } catch (caught) {
      if (caught instanceof Error && /authentication|session/i.test(caught.message)) onLogout();
      else setError(caught instanceof Error ? caught.message : "Workspace data could not be loaded");
    } finally { setLoading(false); }
  }, [onLogout, request]);

  useEffect(() => { void loadWorkspace(); }, [loadWorkspace]);

  const loadAnalytics = useCallback(async () => {
    setAnalyticsLoading(true); setError(null);
    try {
      const report = await request<AnalyticsReport>("/api/v1/analytics/reports", { method: "POST", body: JSON.stringify({}) });
      setAnalyticsReport(report);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Outcome analytics could not be loaded");
    } finally { setAnalyticsLoading(false); }
  }, [request]);

  useEffect(() => {
    if (activeView === "analytics" && !analyticsReport && !analyticsLoading) void loadAnalytics();
  }, [activeView, analyticsLoading, analyticsReport, loadAnalytics]);

  const loadLearning = useCallback(async () => {
    setLearningLoading(true); setError(null);
    try {
      const [policy, models] = await Promise.all([
        request<LearningPolicy>("/api/v1/learning/policy"),
        request<LearningModel[]>("/api/v1/learning/models?limit=20"),
      ]);
      setLearningPolicy(policy); setLearningModels(models);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Learning posture could not be loaded");
    } finally { setLearningLoading(false); }
  }, [request]);

  useEffect(() => {
    if (activeView === "learning" && !learningPolicy && !learningLoading) void loadLearning();
  }, [activeView, learningLoading, learningPolicy, loadLearning]);

  const loadIncident = useCallback(async (incidentId: string) => {
    setSelectedId(incidentId); setBusy(true); setError(null);
    try {
      const incident = await request<IncidentDetail>(`/api/v1/incidents/${incidentId}`);
      setDetail(incident);
      const [match, opportunity, currentAssignment, incidentNotes] = await Promise.all([
        request<PropertyMatch>(`/api/v1/incidents/${incidentId}/property-matches`).catch(() => null),
        request<Opportunity>(`/api/v1/incidents/${incidentId}/opportunity-score`).catch(() => null),
        request<Assignment>(`/api/v1/workflow/incidents/${incidentId}/assignment`).catch(() => null),
        request<WorkflowNote[]>(`/api/v1/workflow/incidents/${incidentId}/notes`).catch(() => []),
      ]);
      setPropertyMatch(match); setScore(opportunity); setAssignment(currentAssignment); setNotes(incidentNotes);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Incident could not be loaded"); }
    finally { setBusy(false); }
  }, [request]);

  const refreshSelected = useCallback(async () => { await loadWorkspace(); if (selectedId) await loadIncident(selectedId); }, [loadIncident, loadWorkspace, selectedId]);

  async function uploadDispatch(file: File, providerId: string, authorized: boolean) {
    setBusy(true); setError(null); setNotice(null);
    try {
      const form = new FormData(); form.append("file", file); form.append("authorized_snapshot", providerId === "sarasota.official_dispatch" ? String(authorized) : "false");
      const imported = await request<ImportJob>(`/api/v1/providers/${encodeURIComponent(providerId)}/snapshots`, { method: "POST", headers: { "Idempotency-Key": `web-${crypto.randomUUID()}` }, body: form });
      await request(`/api/v1/incidents/process/retrievals/${imported.retrieval_id}`, { method: "POST" });
      setNotice(`Snapshot processed: ${imported.normalized_record_count} normalized rows; provenance remains ${imported.acquisition_mode}.`); await loadWorkspace();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Snapshot import failed"); }
    finally { setBusy(false); }
  }

  async function uploadProperty(file: File, providerId: string, sourceVersion: string, authorized: boolean) {
    if (!selectedId) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      const form = new FormData(); form.append("file", file); form.append("provider_id", providerId); form.append("source_version", sourceVersion); form.append("idempotency_key", `web-property-${crypto.randomUUID()}`); form.append("import_mode", "full"); form.append("authorized_snapshot", String(authorized));
      const imported = await request<{ property_import_id: string; normalized_row_count: number; acquisition_mode: string }>("/api/v1/properties/imports", { method: "POST", body: form });
      const match = await request<PropertyMatch>(`/api/v1/incidents/${selectedId}/property-matches`, { method: "POST", body: JSON.stringify({ property_provider_id: providerId, property_import_id: imported.property_import_id }) });
      setPropertyMatch(match); setNotice(`Property file imported with ${imported.normalized_row_count} accepted rows and matched into ${match.candidate_count} candidates.`); await loadWorkspace();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Property import or matching failed"); }
    finally { setBusy(false); }
  }

  async function decideProperty(decision: "confirmed" | "rejected" | "cleared" | "corrected", candidateId?: string) {
    if (!selectedId) return;
    const reason = window.prompt("Record the human-review reason:", decision === "confirmed" ? "Confirmed after reviewing source and parcel evidence." : "Human review decision recorded.");
    if (!reason) return;
    setBusy(true); setError(null);
    try { await request(`/api/v1/incidents/${selectedId}/property-matches/decisions`, { method: "POST", body: JSON.stringify({ decision, candidate_id: candidateId ?? null, reason }) }); setNotice(`Property decision recorded: ${label(decision)}.`); await loadIncident(selectedId); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Property decision failed"); }
    finally { setBusy(false); }
  }

  async function createScore() {
    if (!selectedId) return;
    setBusy(true); setError(null);
    try { const result = await request<Opportunity>(`/api/v1/incidents/${selectedId}/opportunity-score`, { method: "POST", body: JSON.stringify({ property_provider_id: propertyMatch?.property_provider_id ?? null }) }); setScore(result); setNotice("Provisional score generated with its evidence and hard-gate explanation."); await loadWorkspace(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Score generation failed"); }
    finally { setBusy(false); }
  }

  async function changeState(state: string) {
    if (!selectedId) return;
    const reason = window.prompt("Record the reason for this status change:", "Reviewed in the internal workbench.");
    if (!reason) return;
    setBusy(true); setError(null);
    try { const result = await request<IncidentDetail>(`/api/v1/incidents/${selectedId}/state`, { method: "PATCH", body: JSON.stringify({ state, reason }) }); setDetail(result); setIncidents((current) => current.map((item) => item.id === result.id ? result : item)); setNotice(`Incident status changed to ${label(state)}.`); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Status change failed"); }
    finally { setBusy(false); }
  }

  async function generateAlerts() {
    setBusy(true); setError(null); setNotice(null);
    try { const result = await request<{ created_alerts: number; existing_alerts: number; suppressed_alerts: number }>("/api/v1/workflow/alerts/generate", { method: "POST" }); setNotice(`Alert scan complete: ${result.created_alerts} created, ${result.existing_alerts} retained, ${result.suppressed_alerts} suppressed.`); await loadWorkspace(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Alert scan failed"); }
    finally { setBusy(false); }
  }

  async function alertAction(alertId: string, action: "acknowledge" | "snooze" | "resolve" | "suppress" | "revoke" | "escalate" | "unsuppress") {
    const reason = window.prompt("Record the internal workflow reason:", action === "acknowledge" ? "Reviewed in the internal queue." : "Internal workflow decision recorded.");
    if (!reason) return;
    setBusy(true); setError(null);
    const snoozed_until = action === "snooze" ? new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString() : undefined;
    try { await request<WorkflowAlert>(`/api/v1/workflow/alerts/${alertId}/${action}`, { method: "POST", body: JSON.stringify({ reason, snoozed_until }) }); setNotice(`Alert ${label(action)}.`); await loadWorkspace(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Alert action failed"); }
    finally { setBusy(false); }
  }

  async function assignToMe() {
    if (!selectedId || !user) return;
    const reason = window.prompt("Record the assignment reason:", "Assigned for internal review.");
    if (!reason) return;
    setBusy(true); setError(null);
    try { const result = await request<Assignment>(`/api/v1/workflow/incidents/${selectedId}/assignment`, { method: "POST", body: JSON.stringify({ assignee_user_id: user.id, reason }) }); setAssignment(result); setNotice("Incident assigned to the current reviewer."); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Assignment failed"); }
    finally { setBusy(false); }
  }

  async function addWorkflowNote() {
    if (!selectedId) return;
    const body = window.prompt("Add an immutable internal review note:");
    if (!body) return;
    setBusy(true); setError(null);
    try { const note = await request<WorkflowNote>(`/api/v1/workflow/incidents/${selectedId}/notes`, { method: "POST", body: JSON.stringify({ body, note_type: "review" }) }); setNotes((current) => [...current, note]); setNotice("Internal note recorded and audited."); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Note creation failed"); }
    finally { setBusy(false); }
  }

  async function importClients(file: File) {
    setBusy(true); setError(null); setNotice(null);
    try { const form = new FormData(); form.append("file", file); const result = await request<{ accepted_row_count: number; rejected_row_count: number }>("/api/v1/workflow/clients/import", { method: "POST", headers: { "Idempotency-Key": `web-client-${crypto.randomUUID()}` }, body: form }); setNotice(`Existing-client import recorded: ${result.accepted_row_count} accepted, ${result.rejected_row_count} rejected. No outreach was sent.`); await loadWorkspace(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Client import failed"); }
    finally { setBusy(false); }
  }

  const activeLabel = navigation.find((item) => item.id === activeView)?.label ?? "Command center";
  const dispatchProvider = providers.find((provider) => provider.id === "sarasota.official_dispatch") ?? providers.find((provider) => provider.data_type === "dispatch_snapshot");
  const propertyProvider = providers.find((provider) => provider.id === "sarasota.property_appraiser") ?? providers.find((provider) => provider.data_type === "property_bulk_file");
  return <div className="app-shell">
    <aside className="rail" aria-label="Primary navigation"><div className="brand-lockup"><div className="brand-mark" aria-hidden="true"><span /><span /><span /></div><div><p className="brand-name">Beyond</p><p className="brand-product">Fire Radar</p></div></div><div className="rail-rule" /><p className="rail-label">Workspace</p><nav className="nav-list">{navigation.map((item) => <button aria-label={`${item.label}: ${item.detail}`} aria-current={activeView === item.id ? "page" : undefined} className={`nav-item ${activeView === item.id ? "active" : ""}`} key={item.id} onClick={() => setActiveView(item.id)} type="button"><Icon name={item.icon} /><span><strong>{item.label}</strong><small>{item.detail}</small></span></button>)}</nav><div className="rail-bottom"><div className="rail-status"><span className="status-dot status-dot-amber" /><span><strong>Research environment</strong><small>Human review required</small></span></div><button className="user-chip user-chip-button" onClick={onLogout} type="button"><span className="avatar">{user?.display_name.slice(0, 2).toUpperCase() ?? "SA"}</span><span><strong>{user?.display_name ?? "Reviewer"}</strong><small>Sign out</small></span><Icon name="logout" size={15} /></button></div></aside>
    <main className="content"><header className="topbar"><div className="mobile-brand"><div className="brand-mark" aria-hidden="true"><span /><span /><span /></div><strong>Beyond Fire Radar</strong></div><div className="crumbs"><span>Workspace</span><span className="crumb-divider">/</span><strong>{activeLabel}</strong></div><div className="top-actions"><button className="icon-button" aria-label="Refresh workspace" onClick={() => void refreshSelected()} type="button"><Icon name="refresh" /></button><button className="icon-button notification" aria-label="Notifications" type="button"><Icon name="bell" /><span /></button><div className="top-divider" /><SourcePill compact modes={detail?.source_acquisition_modes ?? incidents.flatMap((item) => item.source_acquisition_modes)} /></div></header>
      <div className="workspace"><div className="workspace-head"><div><p className="eyebrow">FIELD OPERATIONS <span>·</span> SARASOTA COUNTY</p><h1>{activeView === "command" ? "Review the signal, keep the uncertainty." : activeLabel}</h1><p className="workspace-lede">{activeView === "command" ? "Inspect source-preserving incidents, property evidence, and provisional research rankings in one governed workspace." : viewDescription(activeView)}</p></div><div className="head-actions"><SourcePill modes={detail?.source_acquisition_modes ?? incidents.flatMap((item) => item.source_acquisition_modes)} /><button className="button button-light" onClick={() => void refreshSelected()} type="button"><Icon name="refresh" size={15} /> Refresh</button></div></div><div className="safety-banner" role="status"><div className="banner-icon"><Icon name="shield" size={17} /></div><div><strong>Research environment</strong><span>Live Sarasota polling is disabled. Manual snapshots only.</span></div><span className="banner-status"><span className="status-dot status-dot-amber" /> Protected</span></div>{error ? <div className="inline-error" role="alert"><Icon name="warning" size={17} /><span><strong>Action needs attention.</strong> {error}</span><button onClick={() => setError(null)} type="button">Dismiss</button></div> : null}{notice ? <div className="inline-success" role="status"><Icon name="check" size={16} /><span>{notice}</span><button onClick={() => setNotice(null)} type="button">Dismiss</button></div> : null}{loading ? <div className="loading-panel"><span className="spinner" /> Loading governed workspace data…</div> : <>{activeView === "command" ? <CommandView incidents={incidents} detail={detail} propertyMatch={propertyMatch} score={score} providers={providers} assignment={assignment} notes={notes} onAssign={assignToMe} onAddNote={addWorkflowNote} opportunities={opportunities} health={health} retrievals={retrievals} dispatchProvider={dispatchProvider} propertyProvider={propertyProvider} busy={busy} onDispatchUpload={uploadDispatch} onSelectIncident={(id) => void loadIncident(id)} onViewStream={() => setActiveView("stream")} onState={changeState} onPropertyUpload={uploadProperty} onPropertyDecision={decideProperty} onScore={createScore} /> : null}{activeView === "stream" ? <StreamView incidents={incidents} detail={detail} propertyMatch={propertyMatch} score={score} providers={providers} busy={busy} assignment={assignment} notes={notes} onAssign={assignToMe} onAddNote={addWorkflowNote} onSelect={(id) => void loadIncident(id)} onState={changeState} onPropertyUpload={uploadProperty} onPropertyDecision={decideProperty} onScore={createScore} onRefresh={() => void refreshSelected()} /> : null}{activeView === "opportunities" ? <OpportunityView opportunities={opportunities} incidents={incidents} onSelect={(id) => void loadIncident(id)} /> : null}{activeView === "workflow" ? <WorkflowView alerts={alerts} busy={busy} onGenerate={generateAlerts} onAction={alertAction} onImportClients={importClients} /> : null}{activeView === "analytics" ? <AnalyticsView report={analyticsReport} loading={analyticsLoading} onRefresh={loadAnalytics} /> : null}{activeView === "learning" ? <LearningView policy={learningPolicy} models={learningModels} loading={learningLoading} onRefresh={loadLearning} /> : null}{activeView === "health" ? <HealthView providers={providers} health={health} retrievals={retrievals} /> : null}{activeView === "settings" ? <SettingsView user={user} onLogout={onLogout} /> : null}</>}</div><footer className="content-footer"><span>Beyond Adjusting · Internal research only</span><span>Source provenance is required for every decision</span></footer></main>
  </div>;
}

function viewDescription(view: View) { return { command: "Inspect source-preserving incidents and evidence.", stream: "Source-preserving incident updates from approved Sarasota snapshots.", opportunities: "Provisional research ranking, never an empirical probability.", workflow: "Internal alerts, assignments, notes, and suppression controls.", analytics: "Manual labels, funnel outcomes, and reproducible directional metrics.", learning: "Versioned learning mechanics remain inactive until real evidence and approval gates pass.", health: "Freshness, provenance, and integration posture at a glance.", settings: "Governance controls for a deliberately constrained workspace." }[view]; }

function CommandView({ incidents, detail, propertyMatch, score, providers, opportunities, health, retrievals, dispatchProvider, propertyProvider, assignment, notes, onAssign, onAddNote, busy, onDispatchUpload, onSelectIncident, onViewStream, onState, onPropertyUpload, onPropertyDecision, onScore }: { incidents: IncidentSummary[]; detail: IncidentDetail | null; propertyMatch: PropertyMatch | null; score: Opportunity | null; providers: Provider[]; opportunities: Opportunity[]; health: Record<string, ProviderHealth>; retrievals: ImportJob[]; dispatchProvider?: Provider; propertyProvider?: Provider; assignment: Assignment | null; notes: WorkflowNote[]; onAssign: () => Promise<void>; onAddNote: () => Promise<void>; busy: boolean; onDispatchUpload: (file: File, providerId: string, authorized: boolean) => Promise<void>; onSelectIncident: (id: string) => void; onViewStream: () => void; onState: (state: string) => Promise<void>; onPropertyUpload: (file: File, providerId: string, sourceVersion: string, authorized: boolean) => Promise<void>; onPropertyDecision: (decision: "confirmed" | "rejected" | "cleared" | "corrected", candidateId?: string) => Promise<void>; onScore: () => Promise<void> }) {
  const reviewCount = incidents.filter((item) => item.review_band !== "auto_linked" || item.contradiction_count > 0).length;
  const currentHealth = dispatchProvider ? health[dispatchProvider.id] : undefined;
  const sourceDate = currentHealth?.last_successful_retrieval ? formatDate(currentHealth.last_successful_retrieval, true) : "Unknown";
  return <><section className="metric-grid" aria-label="Workspace metrics"><Metric label="Canonical incidents" value={String(incidents.length)} note="Current active ledger" /><Metric label="Needs attention" value={String(reviewCount)} note="Review band or contradiction" tone="amber" /><Metric label="Source freshness" value={sourceDate === "Unknown" ? "Unknown" : "Current"} note={sourceDate === "Unknown" ? "No successful snapshot yet" : sourceDate} tone={sourceDate === "Unknown" ? "amber" : "green"} /><Metric label="Opportunities" value={String(opportunities.length)} note="Current score runs; not probabilities" /></section><div className="dashboard-grid"><section className="panel panel-queue" aria-labelledby="queue-title"><div className="panel-heading"><div><p className="section-kicker">REVIEW QUEUE</p><h2 id="queue-title">Canonical incidents</h2></div><button className="text-button" onClick={onViewStream} type="button">Open stream <Icon name="arrow" size={15} /></button></div>{incidents.length === 0 ? <EmptyState title="No canonical incidents loaded" body="Import a permitted Sarasota manual snapshot or select an existing retrieval to begin review." /> : <IncidentRows incidents={incidents.slice(0, 8)} onSelect={onSelectIncident} />}</section><aside className="right-stack"><SnapshotImporter busy={busy} provider={dispatchProvider} onUpload={onDispatchUpload} /><section className="panel source-panel" aria-labelledby="source-title"><div className="panel-heading"><div><p className="section-kicker">SOURCE POSTURE</p><h2 id="source-title">Sarasota dispatch</h2></div><span className="mini-tag">{sourceModeLabel(incidents.flatMap((item) => item.source_acquisition_modes))}</span></div><div className="source-graphic"><div className="source-orbit orbit-one" /><div className="source-orbit orbit-two" /><div className="source-core"><Icon name="database" size={19} /></div></div><div className="source-row"><span>Collection mode</span><strong>{sourceModeLabel(incidents.flatMap((item) => item.source_acquisition_modes))}</strong></div><div className="source-row"><span>Live polling</span><strong className="amber-text">Disabled</strong></div><div className="source-row"><span>Retrievals</span><strong>{retrievals.length}</strong></div><p className="panel-note">{dispatchProvider?.limitations ?? "Provider metadata is unavailable."} Manual availability does not imply legal approval.</p></section><section className="panel principles-panel" aria-labelledby="principles-title"><p className="section-kicker">REVIEW PRINCIPLES</p><h2 id="principles-title">Evidence before escalation.</h2><ul className="principles"><li><span>01</span>Keep raw source rows inspectable.</li><li><span>02</span>Abstain when property evidence is weak.</li><li><span>03</span>Record every human decision.</li></ul></section></aside></div><div className="operations-grid"><section className="panel map-panel" aria-labelledby="map-title"><div className="panel-heading"><div><p className="section-kicker">GEOSPATIAL CONTEXT</p><h2 id="map-title">Incident map</h2></div><span className="soft-label">Source coordinates only</span></div><MapSurface incidents={detail ? [detail] : []} /></section><section className="panel workbench-panel" aria-labelledby="workbench-title"><div className="panel-heading"><div><p className="section-kicker">PROPERTY INTELLIGENCE</p><h2 id="workbench-title">Resolution posture</h2></div><span className="mini-tag">{propertyProvider ? "Manual files" : "Unavailable"}</span></div>{detail ? <IncidentWorkbench busy={busy} detail={detail} match={propertyMatch} score={score} providers={providers} assignment={assignment} notes={notes} onAssign={onAssign} onAddNote={onAddNote} onState={onState} onPropertyUpload={onPropertyUpload} onPropertyDecision={onPropertyDecision} onScore={onScore} /> : <EmptyState title="Select an incident to inspect" body="The workbench exposes original observations, candidate parcels, contradictions, score evidence, and human decisions." />}</section></div></>;
}

function SnapshotImporter({ provider, busy, onUpload }: { provider?: Provider; busy: boolean; onUpload: (file: File, providerId: string, authorized: boolean) => Promise<void> }) {
  const [authorized, setAuthorized] = useState(false);
  const [providerId, setProviderId] = useState(provider?.id ?? "fixture.sarasota.dispatch");
  useEffect(() => { if (provider) setProviderId(provider.id); }, [provider]);
  const official = providerId === "sarasota.official_dispatch";
  return <section className="panel importer-panel" aria-labelledby="import-title"><div className="panel-heading"><div><p className="section-kicker">CONTROLLED IMPORT</p><h2 id="import-title">Add a dispatch snapshot</h2></div><Icon name="upload" size={18} /></div><div className="importer-body"><label>Source<select value={providerId} onChange={(event) => setProviderId(event.target.value)}><option value="fixture.sarasota.dispatch">Repository fixture · test only</option><option disabled={!provider || provider.id !== "sarasota.official_dispatch"} value="sarasota.official_dispatch">Sarasota County · manual snapshot</option></select></label>{official ? <label className="check-label"><input checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} type="checkbox" /> I confirm this file is an approved internal snapshot; this attestation is not legal approval.</label> : <p className="field-note">Fixture imports are labeled synthetic and cannot satisfy operational alert eligibility.</p>}<label className="file-drop"><Icon name="upload" size={16} /><span>Choose CSV, JSON, or HTML snapshot<input accept=".csv,.json,.html,text/csv,application/json,text/html" disabled={busy || (official && !authorized)} onChange={(event) => { const file = event.target.files?.[0]; if (file) void onUpload(file, providerId, authorized); event.currentTarget.value = ""; }} type="file" /></span></label></div></section>;
}

function IncidentRows({ incidents, onSelect }: { incidents: IncidentSummary[]; onSelect: (id: string) => void }) { return <div className="incident-list">{incidents.map((incident) => <button className="incident-row" key={incident.id} onClick={() => onSelect(incident.id)} type="button"><span className={`incident-marker ${incident.contradiction_count ? "amber" : ""}`}><Icon name={incident.contradiction_count ? "warning" : "pulse"} size={15} /></span><span className="incident-row-main"><strong>{incident.canonical_location ?? "Location not resolved"}</strong><small>{label(incident.classification_family)} · {formatDate(incident.first_event_time, true)}</small></span><span className="incident-row-meta"><b>{label(incident.review_band)}</b><small>{incident.observation_count} observations</small></span><Icon name="arrow" size={15} /></button>)}</div>; }

function StreamView({ incidents, detail, propertyMatch, score, providers, busy, assignment, notes, onAssign, onAddNote, onSelect, onState, onPropertyUpload, onPropertyDecision, onScore, onRefresh }: { incidents: IncidentSummary[]; detail: IncidentDetail | null; propertyMatch: PropertyMatch | null; score: Opportunity | null; providers: Provider[]; busy: boolean; assignment: Assignment | null; notes: WorkflowNote[]; onAssign: () => Promise<void>; onAddNote: () => Promise<void>; onSelect: (id: string) => void; onState: (state: string) => Promise<void>; onPropertyUpload: (file: File, providerId: string, sourceVersion: string, authorized: boolean) => Promise<void>; onPropertyDecision: (decision: "confirmed" | "rejected" | "cleared" | "corrected", candidateId?: string) => Promise<void>; onScore: () => Promise<void>; onRefresh: () => void }) {
  const [query, setQuery] = useState("");
  const filtered = incidents.filter((item) => `${item.canonical_location ?? ""} ${item.classification_family} ${item.state}`.toLowerCase().includes(query.toLowerCase()));
  return <div className="stream-layout"><section className="panel stream-panel" aria-labelledby="stream-title"><div className="panel-heading"><div><p className="section-kicker">SOURCE-PRESERVING VIEW</p><h2 id="stream-title">Incident stream</h2></div><div className="view-tools"><label className="search-field"><Icon name="search" size={14} /><input aria-label="Search incidents" onChange={(event) => setQuery(event.target.value)} placeholder="Search location or type" value={query} /></label><button className="button button-light" onClick={onRefresh} type="button"><Icon name="refresh" size={15} /> Refresh</button></div></div>{filtered.length === 0 ? <EmptyState title="No incidents match this view" body="Adjust the search or import a governed Sarasota snapshot. Empty results do not imply that no source data exists." /> : <IncidentRows incidents={filtered} onSelect={onSelect} />}</section>{detail ? <IncidentWorkbench busy={busy} detail={detail} match={propertyMatch} score={score} providers={providers} assignment={assignment} notes={notes} onAssign={onAssign} onAddNote={onAddNote} onState={onState} onPropertyUpload={onPropertyUpload} onPropertyDecision={onPropertyDecision} onScore={onScore} /> : <section className="panel detail-placeholder"><EmptyState title="Select an incident" body="Choose a row to inspect the complete timeline, original observations, provenance, property candidates, and ranking evidence." /></section>}</div>;
}

function IncidentWorkbench({ detail, match, score, providers, busy, assignment, notes, onAssign, onAddNote, onState, onPropertyUpload, onPropertyDecision, onScore }: { detail: IncidentDetail; match: PropertyMatch | null; score: Opportunity | null; providers: Provider[]; busy: boolean; assignment: Assignment | null; notes: WorkflowNote[]; onAssign: () => Promise<void>; onAddNote: () => Promise<void>; onState: (state: string) => Promise<void>; onPropertyUpload: (file: File, providerId: string, sourceVersion: string, authorized: boolean) => Promise<void>; onPropertyDecision: (decision: "confirmed" | "rejected" | "cleared" | "corrected", candidateId?: string) => Promise<void>; onScore: () => Promise<void> }) {
  const [tab, setTab] = useState<"overview" | "evidence" | "property" | "score">("overview");
  const tabs = ["overview", "evidence", "property", "score"] as const;
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  function keydown(event: KeyboardEvent<HTMLButtonElement>, index: number) { const direction = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0; const target = direction ? (index + direction + tabs.length) % tabs.length : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : -1; if (target >= 0) { event.preventDefault(); setTab(tabs[target]); refs.current[target]?.focus(); } }
  return <section className="panel incident-workbench" aria-labelledby="detail-title"><div className="detail-header"><div><p className="section-kicker">INCIDENT WORKBENCH</p><h2 id="detail-title">{detail.canonical_location ?? "Location unresolved"}</h2><p>{label(detail.classification_family)} · {label(detail.confidence_band)} · {detail.source_acquisition_modes.join(", ") || "source mode unknown"}</p></div><div className="detail-actions"><span className={`state-pill ${detail.contradiction_count ? "warning" : ""}`}>{label(detail.state)}</span><select aria-label="Change incident state" disabled={busy} onChange={(event) => { if (event.target.value !== detail.state) void onState(event.target.value); }} value={detail.state}>{["new", "awaiting_review", "property_unresolved", "likely_structure", "high_structure", "confirmed", "Disposition pending", "downgraded", "false_alarm", "closed", "suppressed"].map((state) => <option key={state} value={state}>{label(state)}</option>)}</select></div></div><div className="workflow-strip"><span>{assignment?.assignee_user_id ? `Assigned · ${assignment.assignee_user_id.slice(0, 8)}` : "Unassigned"}</span><button className="button button-light" disabled={busy} onClick={() => void onAssign()} type="button">{assignment?.assignee_user_id ? "Reassign to me" : "Assign to me"}</button><button className="button button-light" disabled={busy} onClick={() => void onAddNote()} type="button">Add note</button><span>{notes.length} internal note{notes.length === 1 ? "" : "s"}</span></div><div className="workbench-tabs" role="tablist" aria-label="Incident detail sections">{tabs.map((item, index) => <button aria-controls="incident-tabpanel" aria-selected={tab === item} className={tab === item ? "active" : ""} id={`incident-tab-${item}`} key={item} onClick={() => setTab(item)} onKeyDown={(event) => keydown(event, index)} ref={(element) => { refs.current[index] = element; }} role="tab" tabIndex={tab === item ? 0 : -1} type="button">{label(item)}</button>)}</div><div className="detail-body" id="incident-tabpanel" role="tabpanel" aria-labelledby={`incident-tab-${tab}`}>{tab === "overview" ? <OverviewTab detail={detail} /> : null}{tab === "evidence" ? <EvidenceTab detail={detail} /> : null}{tab === "property" ? <PropertyPanel busy={busy} match={match} providers={providers} onUpload={onPropertyUpload} onDecision={onPropertyDecision} /> : null}{tab === "score" ? <ScorePanel busy={busy} score={score} onScore={onScore} /> : null}</div></section>;
}

function OverviewTab({ detail }: { detail: IncidentDetail }) { return <div className="detail-columns"><div><div className="detail-facts"><Fact label="Classification" value={label(detail.classification_family)} /><Fact label="Confidence" value={`${Math.round(detail.classification_confidence * 100)}% · ${label(detail.confidence_band)}`} /><Fact label="Event window" value={`${formatDate(detail.first_event_time, true)} → ${formatDate(detail.last_event_time, true)}`} /><Fact label="Observations" value={`${detail.observation_count} source rows`} /></div><section className="subpanel"><div className="subheading"><h3>Incident timeline</h3><span>{detail.timeline.length} events</span></div>{detail.timeline.length ? <div className="timeline">{detail.timeline.map((event, index) => <div className="timeline-item" key={String(event.id ?? index)}><span className="timeline-dot" /><div><strong>{label(String(event.event_type ?? "event"))}</strong><small>{formatDate(String(event.occurred_at ?? ""), true)} · {String(event.details && typeof event.details === "object" ? JSON.stringify(event.details) : event.details ?? "No details")}</small></div></div>)}</div> : <p className="muted-copy">No timeline events are available.</p>}</section></div><div><section className="subpanel"><div className="subheading"><h3>Source posture</h3><span className="mini-tag">Traceable</span></div><p className="muted-copy">Retrievals: {detail.source_retrieval_ids.join(", ") || "not available"}</p><p className="muted-copy">Source modes: {detail.source_acquisition_modes.join(", ") || "not available"}</p><p className="muted-copy">Classification explanation: {String(detail.classification_explanation.summary ?? "Versioned source-faithful classification.")}</p></section><MapSurface incidents={[detail]} /></div></div>; }

function EvidenceTab({ detail }: { detail: IncidentDetail }) { return <div className="detail-columns"><section className="subpanel"><div className="subheading"><h3>Original observations</h3><span>{detail.observations.length} rows</span></div>{detail.observations.length ? <div className="observation-list">{detail.observations.map((observation) => <article className="observation-card" key={observation.id}><strong>{observation.original_event_type}</strong><span>{observation.original_location}</span><small>{formatDate(observation.event_time, true)} · {observation.source_record_id} · parser {observation.parser_version}</small></article>)}</div> : <EmptyState title="No observations available" body="The source relationship is unavailable for this incident." />}</section><section className="subpanel"><div className="subheading"><h3>Contradictions and linkage</h3><span>{detail.evidence.length + detail.match_decisions.length} records</span></div>{detail.evidence.length ? <div className="evidence-list">{detail.evidence.map((item, index) => <article className="evidence-card warning" key={String(item.id ?? index)}><Icon name="warning" size={15} /><div><strong>{label(String(item.code ?? item.evidence_type ?? "evidence"))}</strong><p>{String(item.summary ?? "Source evidence retained.")}</p></div></article>)}</div> : <p className="muted-copy">No contradictory evidence is recorded. Linkage decisions remain available in the source history.</p>}<p className="muted-copy">{detail.current_explanation.summary ? String(detail.current_explanation.summary) : "The canonical incident retains source-row relationships and deterministic/probabilistic explanations."}</p></section></div>; }

function PropertyPanel({ match, providers, busy, onUpload, onDecision }: { match: PropertyMatch | null; providers: Provider[]; busy: boolean; onUpload: (file: File, providerId: string, sourceVersion: string, authorized: boolean) => Promise<void>; onDecision: (decision: "confirmed" | "rejected" | "cleared" | "corrected", candidateId?: string) => Promise<void> }) {
  const propertyProvider = providers.find((provider) => provider.data_type === "property_bulk_file");
  const [authorized, setAuthorized] = useState(false);
  const [sourceVersion, setSourceVersion] = useState("manual-2026-08");
  const official = propertyProvider?.id === "sarasota.property_appraiser";
  return <div className="property-workbench"><section className="subpanel property-import-box"><div className="subheading"><div><h3>Property evidence</h3><p className="muted-copy">Manual/file imports only. Original rows and transformations remain inspectable.</p></div><span className="mini-tag">{match ? `${match.candidate_count} candidates` : "Not resolved"}</span></div>{propertyProvider ? <><div className="inline-form"><label>Source version<input onChange={(event) => setSourceVersion(event.target.value)} value={sourceVersion} /></label>{official ? <label className="check-label"><input checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} type="checkbox" /> Approved internal file attestation</label> : null}<label className="file-drop compact-drop"><Icon name="upload" size={15} /><span>Import property CSV/XLSX/ZIP<input accept=".csv,.xlsx,.zip,text/csv" disabled={busy || (official && !authorized)} onChange={(event) => { const file = event.target.files?.[0]; if (file && propertyProvider) void onUpload(file, propertyProvider.id, sourceVersion, authorized); event.currentTarget.value = ""; }} type="file" /></span></label></div><p className="field-note">{propertyProvider.limitations} No automated official retrieval is enabled.</p></> : <EmptyState title="Property provider unavailable" body="No property bulk-file provider is registered." />}</section>{match ? <><section className="subpanel"><div className="subheading"><h3>Candidate ranking</h3><span className="soft-label">{label(match.status)}</span></div>{match.abstention_reason ? <div className="abstention"><Icon name="warning" size={15} /><span>{match.abstention_reason}</span></div> : null}<div className="candidate-list">{match.candidates.map((candidate) => <article className={`candidate-card ${candidate.is_abstained ? "abstained" : ""}`} key={candidate.id}><div className="candidate-rank">{candidate.rank}</div><div className="candidate-main"><div className="candidate-title"><strong>{candidate.parcel.normalized_address}</strong><span>{label(candidate.classification)}</span></div><p>{candidate.parcel.owner_name ?? "Owner not available"} · Parcel {candidate.parcel.parcel_id}</p><small>Score {candidate.match_score.toFixed(3)}{candidate.score_margin === null ? "" : ` · margin ${candidate.score_margin.toFixed(3)}`} · {candidate.recommendation_status}</small><p className="candidate-explanation">{String(candidate.explanation.summary ?? "Evidence retained in the candidate record.")}</p><div className="candidate-actions"><button className="button button-light" disabled={busy || candidate.is_abstained} onClick={() => void onDecision("confirmed", candidate.id)} type="button">Confirm</button><button className="button button-light" disabled={busy} onClick={() => void onDecision("rejected", candidate.id)} type="button">Reject</button></div></div></article>)}</div></section>{match.current_human_decision ? <div className="decision-banner"><Icon name="check" size={16} /><span>Human decision: {label(String(match.current_human_decision.decision))} · {String(match.current_human_decision.reason ?? "")}</span></div> : null}</> : <EmptyState title="No property match run" body="Import an approved/manual property file to generate candidates. The system will abstain when evidence is insufficient." />}</div>;
}

function ScorePanel({ score, busy, onScore }: { score: Opportunity | null; busy: boolean; onScore: () => Promise<void> }) { return <div className="score-workbench"><section className="subpanel"><div className="subheading"><div><h3>Opportunity ranking</h3><p className="muted-copy">Versioned evidence ranking only; this is not a probability or damage finding.</p></div><button className="button button-dark" disabled={busy} onClick={() => void onScore()} type="button">{score ? "Rescore" : "Generate score"}<Icon name="spark" size={14} /></button></div>{score ? <><div className="score-summary"><div><span className="score-number">{score.provisional_score === null ? "—" : score.provisional_score.toFixed(3)}</span><small>provisional rank</small></div><Fact label="Evidence tier" value={label(score.evidence_tier)} /><Fact label="Hard gate" value={label(score.hard_gate_status)} /><Fact label="Alert eligibility" value={score.alert_eligibility ? "Eligible after governance" : "Not eligible"} /></div>{score.abstention_reason ? <div className="abstention"><Icon name="warning" size={15} /><span>{score.abstention_reason}</span></div> : null}<p className="muted-copy">{String(score.explanation.summary ?? "Every component below retains its evidence and availability boundary.")}</p><div className="feature-list">{score.features.map((feature) => <div className="feature-row" key={feature.id}><span><strong>{label(feature.feature_name)}</strong><small>{feature.explanation}</small></span><b>{feature.value === null ? "Missing" : feature.value.toFixed(3)}</b></div>)}</div></> : <EmptyState title="No score run" body="Generate a versioned provisional ranking after reviewing the incident and property evidence." />}</section></div>; }

function MapSurface({ incidents }: { incidents: Array<IncidentSummary | IncidentDetail> }) { const points = incidents.flatMap((item) => "observations" in item ? item.observations.filter((observation) => observation.latitude !== null && observation.longitude !== null) : []); const lats = points.map((point) => point.latitude as number); const lons = points.map((point) => point.longitude as number); const minLat = lats.length ? Math.min(...lats) : 0; const maxLat = lats.length ? Math.max(...lats) : 1; const minLon = lons.length ? Math.min(...lons) : 0; const maxLon = lons.length ? Math.max(...lons) : 1; const latSpan = Math.max(maxLat - minLat, 0.0001); const lonSpan = Math.max(maxLon - minLon, 0.0001); return <div className="map-empty"><div className="map-grid-lines" aria-hidden="true"><span /><span /><span /><span /></div>{points.length ? <div className="map-points">{points.map((point) => { const left = 12 + (((point.longitude as number) - minLon) / lonSpan) * 76; const top = 86 - (((point.latitude as number) - minLat) / latSpan) * 72; return <span className="map-point" key={point.id} style={{ left: `${left}%`, top: `${top}%` }} title={`${point.latitude}, ${point.longitude}`} />; })}</div> : null}<div className="map-empty-copy">{points.length ? <><div className="empty-mark"><Icon name="pulse" size={20} /></div><h3>{points.length} source coordinate{points.length === 1 ? "" : "s"}</h3><p>Only coordinates supplied by the source are shown. Positions are normalized within this view; no boundary, parcel, or damage inference is drawn.</p></> : <><div className="empty-mark"><Icon name="pulse" size={20} /></div><h3>No source coordinates available</h3><p>This map surface remains empty until an imported observation includes coordinates.</p></>}</div></div>; }

function Fact({ label: title, value }: { label: string; value: string }) { return <div className="fact"><span>{title}</span><strong>{value}</strong></div>; }

function OpportunityView({ opportunities, incidents, onSelect }: { opportunities: Opportunity[]; incidents: IncidentSummary[]; onSelect: (id: string) => void }) { const incidentMap = new Map(incidents.map((incident) => [incident.id, incident])); return <><div className="notice-card"><div className="notice-mark"><Icon name="spark" size={18} /></div><div><strong>Provisional research ranking</strong><p>Scores summarize available evidence. They are not probabilities, damage findings, coverage opinions, or contact recommendations.</p></div><span className="version-tag">Human review</span></div><section className="panel full-panel" aria-labelledby="opportunity-title"><div className="panel-heading"><div><p className="section-kicker">CURRENT SCORE RUNS</p><h2 id="opportunity-title">Opportunity pipeline</h2></div><span className="soft-label">{opportunities.length} loaded</span></div>{opportunities.length ? <div className="opportunity-list">{opportunities.map((opportunity) => { const incident = incidentMap.get(opportunity.incident_id); return <button className="opportunity-row" key={opportunity.id} onClick={() => onSelect(opportunity.incident_id)} type="button"><span className="opportunity-score">{opportunity.provisional_score === null ? "—" : opportunity.provisional_score.toFixed(3)}</span><span><strong>{incident?.canonical_location ?? "Location unresolved"}</strong><small>{label(opportunity.evidence_tier)} · {label(opportunity.hard_gate_status)} · {opportunity.alert_eligibility ? "eligible" : "not eligible"}</small></span><Icon name="arrow" size={15} /></button>; })}</div> : <EmptyState title="No opportunity score runs" body="Generate a provisional score from an incident workbench after reviewing property evidence. No count or probability is implied by this empty state." />}</section></>; }

function WorkflowView({ alerts, busy, onGenerate, onAction, onImportClients }: { alerts: WorkflowAlert[]; busy: boolean; onGenerate: () => Promise<void>; onAction: (alertId: string, action: "acknowledge" | "snooze" | "resolve" | "suppress" | "revoke" | "escalate" | "unsuppress") => Promise<void>; onImportClients: (file: File) => Promise<void> }) { return <div className="workflow-grid"><section className="panel full-panel" aria-labelledby="workflow-title"><div className="panel-heading"><div><p className="section-kicker">INTERNAL REVIEW QUEUE</p><h2 id="workflow-title">Alerts and workflow</h2></div><div className="workflow-actions"><button className="button button-dark" disabled={busy} onClick={() => void onGenerate()} type="button"><Icon name="refresh" size={15} /> Scan eligible scores</button><label className="file-drop compact-drop"><Icon name="upload" size={15} /><span>Import existing-client CSV<input accept=".csv,text/csv" disabled={busy} onChange={(event) => { const file = event.target.files?.[0]; if (file) void onImportClients(file); event.currentTarget.value = ""; }} type="file" /></span></label></div></div><div className="workflow-boundary"><Icon name="shield" size={15} /><span>In-app review only. Suppression wins. No email, SMS, phone, owner contact, or consumer outreach is implemented.</span></div>{alerts.length ? <div className="alert-list">{alerts.map((alert) => <article className={`alert-card ${alert.status}`} key={alert.id}><div><span className="mini-tag">{label(alert.status)}</span><h3>{alert.title}</h3><p>{alert.summary}</p><small>{formatDate(alert.created_at, true)} · {label(alert.severity)} · score {String(alert.evidence_snapshot.provisional_score ?? "not recorded")}</small>{alert.suppression_reason ? <small>Suppression: {alert.suppression_reason}</small> : null}</div><div className="alert-actions">{alert.status === "open" || alert.status === "snoozed" ? <button className="button button-light" disabled={busy} onClick={() => void onAction(alert.id, "acknowledge")} type="button">Acknowledge</button> : null}{alert.status === "open" || alert.status === "acknowledged" ? <button className="button button-light" disabled={busy} onClick={() => void onAction(alert.id, "snooze")} type="button">Snooze 1 day</button> : null}{alert.status === "open" || alert.status === "acknowledged" || alert.status === "snoozed" ? <button className="button button-light" disabled={busy} onClick={() => void onAction(alert.id, "escalate")} type="button">Escalate</button> : null}{alert.status !== "suppressed" && alert.status !== "revoked" && alert.status !== "resolved" ? <button className="button button-light" disabled={busy} onClick={() => void onAction(alert.id, "suppress")} type="button">Suppress</button> : null}{alert.status === "acknowledged" || alert.status === "escalated" ? <button className="button button-light" disabled={busy} onClick={() => void onAction(alert.id, "resolve")} type="button">Resolve</button> : null}{alert.status === "suppressed" ? <button className="button button-light" disabled={busy} onClick={() => void onAction(alert.id, "unsuppress")} type="button">Re-open</button> : null}{alert.status !== "suppressed" && alert.status !== "revoked" && alert.status !== "resolved" ? <button className="button button-light" disabled={busy} onClick={() => void onAction(alert.id, "revoke")} type="button">Revoke</button> : null}</div></article>)}</div> : <EmptyState title="No internal alerts" body="Only explicitly eligible, authorized manual-source scores can create an alert. Fixture and unauthorized data remain review-only and produce no operational alert." />}</section></div>; }

function AnalyticsView({ report, loading, onRefresh }: { report: AnalyticsReport | null; loading: boolean; onRefresh: () => Promise<void> }) {
  function metricValue(metric: AnalyticsMetric) {
    if (metric.value === null) return metric.status === "blocked" ? "Blocked" : "Distribution";
    return `${(metric.value * 100).toFixed(1)}%`;
  }
  return <div className="analytics-grid"><section className="notice-card"><div className="notice-mark"><Icon name="database" size={18} /></div><div><strong>Directional internal analytics</strong><p>Labels and events are manually recorded and reproducible from a saved manifest. These numbers are not real-world accuracy, calibration, damage, coverage, claim-validity, or conversion claims.</p></div><button className="button button-light" disabled={loading} onClick={() => void onRefresh()} type="button"><Icon name="refresh" size={15} /> Rebuild report</button></section>{loading ? <div className="loading-panel"><span className="spinner" /> Building the current evaluation manifest…</div> : report ? <><section className="panel full-panel" aria-labelledby="analytics-title"><div className="panel-heading"><div><p className="section-kicker">REPRODUCIBLE MANIFEST</p><h2 id="analytics-title">Outcomes and analytics</h2></div><span className="soft-label">{report.manifest.incident_ids.length} incidents · {report.manifest.label_ids.length} labels</span></div><div className="analytics-boundary"><span>As of {formatDate(report.manifest.as_of, true)}</span><span>Source modes: {report.manifest.source_acquisition_modes.length ? report.manifest.source_acquisition_modes.map(label).join(", ") : "none"}</span><span>Dispatch retrievals: {report.manifest.source_retrieval_ids.length} · property imports: {report.manifest.source_property_import_ids.length}</span><span>Claim status: {label(report.manifest.claim_status)}</span></div><div className="analytics-metrics">{report.metrics.map((metric) => <article className="analytics-card" key={metric.id}><div className="subheading"><h3>{label(metric.metric_name)}</h3><span className={`mini-tag ${metric.status === "available" ? "" : "amber"}`}>{label(metric.status)}</span></div><strong className="analytics-value">{metricValue(metric)}</strong><p className="muted-copy">{metric.numerator === null ? `${metric.denominator} denominator · distribution/readiness output` : `${metric.numerator} numerator · ${metric.denominator} denominator`}</p>{metric.warning ? <p className="field-note"><Icon name="warning" size={13} /> {metric.warning}</p> : null}{metric.metric_name === "model_lab_readiness" ? <p className="field-note">No learned model was trained. Real held-out labels, time-aware splits, leakage checks, and administrator approval remain required.</p> : null}</article>)}</div></section><section className="panel full-panel"><div className="subheading"><h3>Manifest evidence</h3><span className="mini-tag">Immutable references</span></div><p className="muted-copy">Manifest {report.manifest.id} fixes the incident, score-run, label, and outcome-event IDs used by this report. It also retains dispatch retrieval and property-import provenance, including provider, authorization, and snapshot references. Rebuilding later creates a new manifest; prior results are not overwritten.</p></section></> : <EmptyState title="No analytics report" body="The current report could not be generated. No metric is implied by this empty state." />}</div>;
}

function LearningView({ policy, models, loading, onRefresh }: { policy: LearningPolicy | null; models: LearningModel[]; loading: boolean; onRefresh: () => Promise<void> }) {
  return <div className="analytics-grid"><section className="notice-card"><div className="notice-mark"><Icon name="shield" size={18} /></div><div><strong>Governed learning posture</strong><p>Feature and label contracts, time-aware grouped splits, leakage checks, replay, drift, and rollback mechanics are available. Learned scoring is not active.</p></div><button className="button button-light" disabled={loading} onClick={() => void onRefresh()} type="button"><Icon name="refresh" size={15} /> Refresh posture</button></section>{loading ? <div className="loading-panel"><span className="spinner" /> Loading model-release posture…</div> : policy ? <><section className="panel full-panel" aria-labelledby="learning-title"><div className="panel-heading"><div><p className="section-kicker">MODEL RELEASE CONTROL</p><h2 id="learning-title">Model lab</h2></div><span className={`mini-tag ${policy.learned_model_active ? "" : "amber"}`}>{policy.learned_model_active ? "Active" : "Fallback"}</span></div><div className="learning-summary"><div className="learning-status"><span className="section-kicker">Current policy</span><strong>{label(policy.mode)}</strong><p>{policy.reason}</p></div><div className="fact"><span>Learned model</span><strong>{policy.learned_model_active ? policy.model_release_id ?? "Approved release" : "Not active"}</strong></div><div className="fact"><span>Probability display</span><strong>{policy.probability_display ? "Enabled" : "Off"}</strong></div></div><div className="learning-boundary"><Icon name="lock" size={15} /><span>Activation requires real approved outcomes, valid held-out improvement, calibration, improved top-alert precision, complete error analysis, and explicit administrator approval. Current releases cannot activate from this screen.</span></div></section><section className="panel full-panel"><div className="panel-heading"><div><p className="section-kicker">VERSIONED RELEASES</p><h2>Training history</h2></div><span className="soft-label">{models.length} release{models.length === 1 ? "" : "s"}</span></div>{models.length ? <div className="learning-model-list">{models.map((model) => <article className="learning-model" key={model.id}><div><strong>{model.model_version}</strong><small>{label(model.algorithm)} · dataset {model.dataset_snapshot_id}</small></div><span className={`mini-tag ${model.status === "champion" ? "" : "amber"}`}>{label(model.status)}</span><p>{model.inactive_reason ?? "Release remains subject to the explicit approval gate."}</p><small>Feature set {model.feature_set_id} · label set {model.label_set_id} · created {formatDate(model.created_at, true)}</small></article>)}</div> : <EmptyState title="No model releases" body="No learned release has been trained from the current evidence set. Rule-based fallback remains the only serving path." />}</section></> : <EmptyState title="Learning posture unavailable" body="The policy endpoint did not return a status. No learned model is assumed active." />}</div>;
}

function HealthView({ providers, health, retrievals }: { providers: Provider[]; health: Record<string, ProviderHealth>; retrievals: ImportJob[] }) { return <div className="health-grid"><section className="panel full-panel" aria-labelledby="health-title"><div className="panel-heading"><div><p className="section-kicker">INTEGRATION POSTURE</p><h2 id="health-title">Data health</h2></div><span className="soft-label">{retrievals.length} retrievals</span></div><div className="health-list">{providers.map((provider) => { const status = health[provider.id]; return <div className="health-row" key={provider.id}><span className={`health-dot ${status?.last_retrieval_status === "imported" ? "green" : "amber"}`} /><div><strong>{provider.name}</strong><small>{provider.data_type} · {provider.authorized_use_status}</small></div><span className="health-status amber">{provider.id.includes("official") ? "Manual only" : status?.last_retrieval_status ?? "No retrieval"}</span></div>; })}</div></section><section className="panel health-note-panel"><div className="large-lock"><Icon name="lock" size={21} /></div><p className="section-kicker">PROVENANCE</p><h2>Every retrieval stays inspectable.</h2><p>Latest status, parser/schema metadata, replay state, errors, and acquisition mode remain available from this workspace.</p>{retrievals.slice(0, 5).map((retrieval) => <p className="health-retrieval" key={retrieval.retrieval_id}><strong>{formatDate(retrieval.created_at, true)}</strong> · {label(retrieval.status)} · {retrieval.normalized_record_count} rows · {label(retrieval.acquisition_mode)}</p>)}</section></div>; }

function SettingsView({ user, onLogout }: { user: { display_name: string; email: string; roles: string[] } | null; onLogout: () => void }) { return <div className="settings-grid"><section className="panel full-panel" aria-labelledby="settings-title"><div className="panel-heading"><div><p className="section-kicker">CONTROLLED CONFIGURATION</p><h2 id="settings-title">Settings</h2></div><span className="mini-tag">Authenticated</span></div><div className="settings-list"><SettingRow label="Live Sarasota polling" detail="External approval and feature flag required" value="Disabled" /><SettingRow label="Automatic consumer outreach" detail="Not implemented by policy" value="Unavailable" /><SettingRow label="Probability display" detail="Only calibrated real-world models may use probability language" value="Off" /><SettingRow label="Human review" detail="Required for unresolved or contradictory evidence" value="Required" /><SettingRow label="Session identity" detail={user?.email ?? "Unknown"} value={user?.roles.join(", ") ?? "Unknown"} /></div></section><section className="panel settings-side"><div className="avatar large-avatar">{user?.display_name.slice(0, 2).toUpperCase() ?? "SA"}</div><p className="section-kicker">CURRENT SESSION</p><h2>{user?.display_name ?? "Reviewer"}</h2><p className="panel-note">Server-side role checks govern every import, correction, score, workflow, and audit action.</p><button className="button button-light" onClick={onLogout} type="button"><Icon name="logout" size={15} /> Sign out</button></section></div>; }

function SettingRow({ label: title, detail, value }: { label: string; detail: string; value: string }) { return <div className="setting-row"><div><strong>{title}</strong><small>{detail}</small></div><span className="setting-value">{value}</span></div>; }
