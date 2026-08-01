export interface SourceMeta {
  source: string;
  source_url?: string | null;
  observation_time?: string | null;
  fetched_at: string;
  stale: boolean;
  demo: boolean;
  warnings: string[];
  cache_age_seconds?: number | null;
  market_status: "pre_open" | "trading" | "session_break" | "closed" | "non_trading_day" | "daily" | "unknown";
  market_status_label: string;
  data_state: "live" | "latest" | "cached" | "stale" | "demo";
  quality_score: number;
  quality_issues: string[];
  trust_level: "trusted" | "partial" | "suspicious" | "unavailable";
  suspicious_rows: number;
}

export interface Dataset<T> {
  data: T;
  meta: SourceMeta;
}

export interface RateItem {
  name: string;
  tenor: string;
  value: number | null;
  change_bp: number | null;
}

export interface CurveSeries {
  name: string;
  values: Array<number | null>;
}

export interface CurveData {
  tenors: string[];
  series: CurveSeries[];
  changes: Array<number | null>;
  history?: Array<{
    date: string;
    values: Record<string, number | null>;
    spreads_bp: Record<string, number | null>;
  }>;
}

export interface HistoryResponse {
  adapter: string;
  metric: string;
  unit: string;
  dates: string[];
  series: Array<CurveSeries & { key: string }>;
}

export interface SpotBond {
  code: string;
  name: string;
  type: string;
  yield: number | null;
  change_bp: number | null;
  price: number | null;
  volume: number | null;
  code_available?: boolean;
  code_verified?: boolean;
  code_source?: "source" | "standard_name_rule" | "unavailable";
  type_inferred?: boolean;
  quality_state?: "trusted" | "partial" | "suspicious";
  quality_issues?: string[];
}

export interface TreasuryFuture {
  product: string;
  contract: string;
  price: number | null;
  change_pct: number | null;
  volume: number;
  open_interest: number;
}

export interface FxPairQuote {
  code: string;
  pair: string;
  name: string;
  bid: number | null;
  ask: number | null;
  mid: number | null;
  spread_pips: number | null;
  change_pct: number | null;
}

export interface FxRmbReference {
  code: string;
  name: string;
  base: string;
  quote: "CNY";
  display_basis: number;
  mid: number | null;
  bid: number | null;
  ask: number | null;
  change_pct: number | null;
  observation_date: string;
  reference_type: string;
  history: Array<{ date: string; mid: number | null }>;
}

export interface Convertible {
  code: string;
  name: string;
  price: number | null;
  change_pct: number | null;
  stock_name: string;
  convert_value: number | null;
  premium_pct: number | null;
  double_low: number | null;
  ytm_pct: number | null;
  redeem_status: string;
  data_tier?: "comparison" | "partial_comparison" | "price_only";
  field_coverage?: number;
  research_eligible?: boolean;
  quality_state?: "trusted" | "partial" | "suspicious";
  quality_issues?: string[];
}

export interface MarketEvent {
  date: string;
  type: string;
  title: string;
  importance: "high" | "medium" | "low";
}

export interface HealthItem {
  adapter: string;
  label: string;
  state: "healthy" | "cached" | "degraded" | "unavailable" | "not_checked";
  last_success_at?: string | null;
  last_failure_at?: string | null;
  observation_time?: string | null;
  rows: number;
  latency_ms?: number | null;
  message?: string | null;
  last_attempt_at?: string | null;
  consecutive_failures: number;
  cache_age_seconds?: number | null;
  cache_persisted: boolean;
  market_status: "pre_open" | "trading" | "session_break" | "closed" | "non_trading_day" | "daily" | "unknown";
  market_status_label: string;
  quality_score: number;
  quality_issues: string[];
  trust_level: "trusted" | "partial" | "suspicious" | "unavailable";
  suspicious_rows: number;
  execution_mode: "isolated_process" | "in_process_http" | "local_demo";
  refreshing: boolean;
  circuit_state: "closed" | "open" | "half_open";
  next_retry_at?: string | null;
  next_refresh_at?: string | null;
  research_status: "ready" | "limited" | "blocked" | "unchecked";
}

export interface WatchlistItem {
  id: number;
  object_type: "bond" | "future" | "convertible" | "macro" | "fx";
  object_id: string;
  name: string;
  note: string;
  group_name: string;
  tags: string[];
  research_status: ResearchStatus;
  pinned: boolean;
  next_review_date?: string | null;
  created_at: string;
  updated_at: string;
}

export type ResearchStatus = "draft" | "tracking" | "formed" | "review" | "archived";

export interface ResearchEvidence {
  id: number;
  project_id: number;
  evidence_type: "chart" | "table" | "snapshot" | "note";
  title: string;
  payload: Record<string, unknown>;
  source_summary: string;
  observation_start?: string | null;
  observation_end?: string | null;
  created_at: string;
}

export interface ResearchProject {
  id: number;
  title: string;
  question: string;
  hypothesis: string;
  status: ResearchStatus;
  confidence: number;
  horizon: string;
  tags: string[];
  next_review_date?: string | null;
  conclusion: string;
  created_at: string;
  updated_at: string;
  evidence: ResearchEvidence[];
  activity: ResearchProjectActivity[];
  entries: ResearchEntry[];
}

export type ResearchObjectType =
  | "rates_theme"
  | "macro_theme"
  | "country"
  | "issuer"
  | "security"
  | "release_event";

export type ResearchTopicStatus = "active" | "review" | "archived";

export type ResearchTopicComponentType =
  | "market_pulse"
  | "market_history"
  | "fred_chart"
  | "sovereign_compare"
  | "event_radar"
  | "project_summary"
  | "recent_evidence";

export interface ResearchTopicComponent {
  id: string;
  component_type: ResearchTopicComponentType;
  title: string;
  config: Record<string, unknown>;
  order: number;
}

export interface ResearchObject {
  id: number;
  object_type: ResearchObjectType;
  object_key: string;
  name: string;
  description: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface ResearchTopicProject {
  id: number;
  title: string;
  status: ResearchStatus;
  confidence: number;
  next_review_date?: string | null;
  updated_at: string;
}

export interface ResearchTopic {
  id: number;
  title: string;
  question: string;
  description: string;
  status: ResearchTopicStatus;
  tags: string[];
  components: ResearchTopicComponent[];
  research_object: ResearchObject;
  projects: ResearchTopicProject[];
  created_at: string;
  updated_at: string;
}

export interface ResearchTopicTemplate {
  id: "china_rates" | "sino_us_rates" | "rmb_rates" | "global_inflation" | "blank";
  name: string;
  description: string;
  title: string;
  question: string;
  object_type: ResearchObjectType;
  object_key: string;
  object_name: string;
  tags: string[];
  components: ResearchTopicComponent[];
}

export interface ResearchTopicTimelineItem {
  id: string;
  event_type: string;
  title: string;
  summary: string;
  project_id: number;
  project_title: string;
  event_time: string;
  observation_time?: string | null;
  metadata: Record<string, unknown>;
}

export interface ResearchProjectSummary {
  project_id: number;
  title: string;
  status: ResearchStatus;
  confidence: number;
  question: string;
  hypothesis: string;
  conclusion: string;
  supporting_evidence: Array<{
    id: number;
    title: string;
    source: string;
    observation_end?: string | null;
    created_at: string;
  }>;
  counter_evidence: Array<{
    id: number;
    title: string;
    content: string;
    status: "open" | "done";
    updated_at: string;
  }>;
  open_tasks: Array<{
    id: number;
    title: string;
    due_date?: string | null;
    content: string;
  }>;
  recent_conclusion_changes: Array<Record<string, unknown>>;
  next_review_date?: string | null;
  gaps: string[];
  generated_at: string;
  notice: string;
}

export interface ResearchTopicWorkspace {
  topic: ResearchTopic;
  timeline: ResearchTopicTimelineItem[];
  timeline_total: number;
  timeline_has_more: boolean;
  timeline_next_cursor: ResearchTopicTimelineCursor | null;
  project_summaries: ResearchProjectSummary[];
  generated_at: string;
}

export interface ResearchTopicTimelineCursor {
  event_time: string;
  id: string;
}

export interface ResearchTopicTimelinePage {
  items: ResearchTopicTimelineItem[];
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
  next_cursor: ResearchTopicTimelineCursor | null;
}

export interface EvidenceBasketItem {
  id: number;
  evidence_type: ResearchEvidence["evidence_type"];
  title: string;
  payload: Record<string, unknown>;
  source_summary: string;
  observation_start?: string | null;
  observation_end?: string | null;
  origin_page: string;
  topic_id?: number | null;
  research_object_id?: number | null;
  created_at: string;
}

export interface GdeltEventItem {
  id: string;
  title: string;
  url: string;
  domain: string;
  seen_at?: string | null;
  language: string;
  source_country: string;
  image_url?: string | null;
}

export interface GdeltEventRadarData {
  query: string;
  days: number;
  sort: "datedesc" | "hybridrel";
  article_count: number;
  source_count: number;
  country_count: number;
  latest_seen_at?: string | null;
  source_distribution: Array<{ name: string; count: number }>;
  country_distribution: Array<{ name: string; count: number }>;
  articles: GdeltEventItem[];
  storage_mode: "metadata_cache";
  verification_status: "unverified_clue";
  attribution: string;
  license_url: string;
  notice: string;
}

export interface ConnectorItem {
  id: "akshare" | "fred" | "world_bank" | "gdelt";
  name: string;
  category: "market" | "macro" | "sovereign" | "events";
  state: HealthItem["state"];
  research_status: HealthItem["research_status"];
  enabled: boolean;
  access_mode: "public" | "user_api_key";
  credential_configured: boolean;
  credential_source: "none" | "environment" | "keychain" | "not_required";
  capabilities: string[];
  storage_mode: "persistent_cache" | "request_scoped" | "mixed_upstream_cache" | "metadata_cache";
  cache_ttl_seconds?: number | null;
  persistence_notice: string;
  license_name: string;
  license_url: string;
  attribution: string;
  terms_url: string;
  docs_url: string;
  quota_notice: string;
  boundary_notice: string;
  last_success_at?: string | null;
  cache_rows: number;
  adapter_count: number;
  available_adapters: number;
}

export interface ConnectorCatalog {
  generated_at: string;
  connectors: ConnectorItem[];
  policy: string;
}

export type ResearchEntryType = "note" | "counter_evidence" | "task" | "review";

export interface ResearchEntry {
  id: number;
  project_id: number;
  entry_type: ResearchEntryType;
  title: string;
  content: string;
  status: "open" | "done";
  due_date?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ResearchActionDraft {
  id: number;
  project_id: number;
  action_type: "task" | "counter_evidence" | "review";
  title: string;
  content: string;
  status: "proposed" | "accepted" | "dismissed" | "undone";
  source: string;
  source_reference: string;
  created_entry_id?: number | null;
  created_at: string;
  updated_at: string;
}

export interface ResearchActionDraftResponse {
  items: ResearchActionDraft[];
  proposed: number;
  accepted: number;
  notice: string;
}

export interface ResearchProjectActivity {
  id: number;
  project_id: number;
  event_type: "created" | "updated" | "evidence_added" | "evidence_removed" | "entry_added" | "entry_updated" | "entry_removed" | "imported";
  summary: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface MarketResearchSignal {
  id: string;
  category: "funding" | "curve" | "future" | "bond";
  severity: "high" | "watch" | "info";
  direction: "up" | "down" | "neutral";
  title: string;
  summary: string;
  value: number | null;
  unit: string;
  object_type?: string | null;
  object_id?: string | null;
  object_name?: string | null;
  adapter: string;
  source: string;
  source_url?: string | null;
  observation_time?: string | null;
  fetched_at: string;
  trust_level: SourceMeta["trust_level"];
  quality_score: number;
  data_state: SourceMeta["data_state"];
  demo: boolean;
  actionable: boolean;
  threshold?: number | null;
  trigger_reason: string;
}

export interface ResearchSignalSettings {
  funding_change_bp: number;
  curve_change_bp: number;
  curve_spread_bp: number;
  futures_change_pct: number;
  bond_change_bp: number;
}

export interface MarketResearchBrief {
  generated_at: string;
  market_status: string;
  headline: string;
  signals: MarketResearchSignal[];
  sources: Array<{
    adapter: string;
    source: string;
    source_url?: string | null;
    observation_time?: string | null;
    fetched_at: string;
    data_state: SourceMeta["data_state"];
    trust_level: SourceMeta["trust_level"];
    quality_score: number;
    demo: boolean;
  }>;
  eligible_signal_ids: string[];
  snapshot_eligible: boolean;
  notice: string;
  settings: ResearchSignalSettings;
}

export interface ResearchTemplate {
  id: "blank" | "rates_direction" | "macro_release" | "convertible_event" | "credit_observation" | "sovereign_comparison";
  name: string;
  description: string;
  title: string;
  question: string;
  hypothesis: string;
  horizon: string;
  tags: string[];
}

export interface EnrichedWatchlistItem extends WatchlistItem {
  page: "bonds" | "futures" | "convertibles" | "macro" | "fx";
  quote?: {
    primary_label: string;
    primary_value?: number | null;
    primary_unit: string;
    change_label: string;
    change_value?: number | null;
    change_unit: string;
    premium_pct?: number | null;
    ytm_pct?: number | null;
  } | null;
  source_meta?: {
    source: string;
    observation_time?: string | null;
    fetched_at: string;
    data_state: SourceMeta["data_state"];
    trust_level: SourceMeta["trust_level"];
    quality_score: number;
    market_status: string;
    demo: boolean;
  } | null;
  quote_status: "available" | "not_found" | "request_required";
}

export interface WeeklyReport {
  start_date: string;
  end_date: string;
  generated_at: string;
  summary: {
    active_projects: number;
    projects_updated: number;
    notes: number;
    counter_evidence: number;
    tasks_done: number;
    tasks_open: number;
    release_reviews: number;
  };
  due_projects: Array<Record<string, unknown>>;
  projects: Array<Record<string, unknown>>;
  activity: Array<Record<string, unknown>>;
  entries: Array<Record<string, unknown>>;
  open_tasks: Array<Record<string, unknown>>;
  conclusion_updates: Array<Record<string, unknown>>;
  next_reviews: Array<Record<string, unknown>>;
  release_reviews: Array<Record<string, unknown>>;
  notice: string;
}

export interface ReleaseReview {
  id: number;
  title: string;
  series_id: string;
  release_name: string;
  release_date: string;
  observation_period: string;
  expected_value: number;
  expected_unit: string;
  project_id?: number | null;
  pre_window_days: number;
  post_window_days: number;
  notes: string;
  reviewed_realtime_start?: string | null;
  reviewed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReleaseEvaluation {
  review: ReleaseReview;
  actual: {
    value?: number | null;
    date?: string | null;
    realtime_start?: string | null;
    realtime_end?: string | null;
    fetched_at: string;
    source: string;
    source_url?: string | null;
    persisted: false;
  };
  surprise?: number | null;
  revision_status: "not_reviewed" | "unchanged" | "official_version_changed";
  market_window: {
    event_date: string;
    start: string;
    end: string;
    series: Array<{
      adapter: string;
      series_key: string;
      metric: string;
      label: string;
      before?: Record<string, unknown> | null;
      after?: Record<string, unknown> | null;
      change?: number | null;
    }>;
    notice: string;
  };
  storage_notice: string;
}

export interface CreditCoverageItem {
  id: number;
  bond_code: string;
  bond_name: string;
  issuer: string;
  canonical_issuer: string;
  sector: string;
  region: string;
  issuer_type: string;
  maturity_date?: string | null;
  put_date?: string | null;
  rating: string;
  rating_date?: string | null;
  yield_pct?: number | null;
  yield_observation_date?: string | null;
  benchmark_tenor?: "1Y" | "3Y" | "5Y" | "7Y" | "10Y" | null;
  benchmark_yield_pct?: number | null;
  benchmark_observation_date?: string | null;
  source_note: string;
  next_review_date?: string | null;
  watch_status: "active" | "watch" | "review" | "archived";
  normalized_issuer: string;
  remaining_years?: number | null;
  eligible: boolean;
  spread_bp?: number | null;
  missing_fields: string[];
  gate_reasons: string[];
  calculation_notice: string;
  history?: CreditHistoryItem[];
  history_points?: number;
  spread_change_bp?: number | null;
  spread_percentile?: number | null;
  created_at: string;
  updated_at: string;
}

export interface CreditHistoryItem {
  history_id: number;
  observation_id: number;
  rating: string;
  rating_date?: string | null;
  yield_pct?: number | null;
  yield_observation_date?: string | null;
  benchmark_tenor?: string | null;
  benchmark_yield_pct?: number | null;
  benchmark_observation_date?: string | null;
  spread_bp?: number | null;
  eligible: boolean;
  source_note: string;
  recorded_at: string;
}

export interface CreditCoverage {
  total: number;
  eligible: number;
  blocked: number;
  eligible_ratio: number;
  field_coverage: Record<string, { covered: number; total: number; ratio: number }>;
  items: CreditCoverageItem[];
  policy: string;
}

export interface CreditSignal {
  id: string;
  kind: string;
  level: "high" | "watch" | "info";
  title: string;
  detail: string;
  bond_code: string;
  bond_name: string;
  issuer: string;
  observation_date?: string | null;
  source_note: string;
  quality_state: "confirmed_input" | "missing_source";
  requires_manual_confirmation: true;
  confirmation?: { signal_id: string; note: string; confirmed_at: string } | null;
}

export interface CreditIssuerSummary {
  issuer: string;
  bond_count: number;
  eligible_count: number;
  ratings: string[];
  spread_range_bp?: { minimum: number; maximum: number; count: number } | null;
  next_event?: CreditCalendarEvent | null;
  sector: string;
  region: string;
  issuer_type: string;
  observation_ids: number[];
}

export interface CreditCalendarEvent {
  date: string;
  kind: "rating_review" | "put" | "maturity" | "review";
  title: string;
  bond_code: string;
  issuer: string;
  overdue: boolean;
}

export interface CreditPortfolio {
  id: number;
  name: string;
  description: string;
  observation_ids: number[];
  members: CreditCoverageItem[];
  eligible_count: number;
  spread_range_bp?: { minimum: number; maximum: number; count: number } | null;
  issuer_count: number;
  created_at: string;
  updated_at: string;
}

export interface CreditWorkspace extends CreditCoverage {
  issuers: CreditIssuerSummary[];
  portfolios: CreditPortfolio[];
  signals: CreditSignal[];
  calendar: CreditCalendarEvent[];
  summary: {
    issuers: number;
    portfolios: number;
    history_points: number;
    unconfirmed_signals: number;
  };
  as_of: string;
  r2_policy: string;
}

export interface CreditImportPreview {
  filename: string;
  headers: string[];
  mapping: Record<string, string>;
  fields: Array<{ field: string; label: string; required: boolean }>;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  errors: Array<{ row: number; message: string }>;
  preview_rows: Array<{
    row: number;
    bond_code: string;
    bond_name: string;
    issuer: string;
    yield_observation_date?: string | null;
    eligible: boolean;
    quality_notes: string[];
  }>;
  notice: string;
  committed: boolean;
  imported_rows?: number;
  observations?: number;
}

export interface CreditCandidates {
  candidates: Array<{
    bond_code: string;
    bond_name: string;
    yield_pct: number;
    yield_observation_date?: string | null;
    source: string;
  }>;
  benchmark_curve: {
    observation_date?: string | null;
    values: Record<string, number>;
    source?: string | null;
    eligible: boolean;
    observation_time?: string | null;
    data_state: SourceMeta["data_state"] | "unavailable";
    trust_level: SourceMeta["trust_level"];
    quality_score: number;
    gate_reasons: string[];
  };
  candidate_source: {
    eligible: boolean;
    source?: string | null;
    observation_time?: string | null;
    data_state: SourceMeta["data_state"] | "unavailable";
    trust_level: SourceMeta["trust_level"];
    quality_score: number;
    gate_reasons: string[];
  };
  notice: string;
}

export interface FredIntegrationStatus {
  provider: "fred";
  configured: boolean;
  verified: boolean;
  verification_state: "not_configured" | "unverified" | "verified" | "failed";
  last_verified_at?: string | null;
  credential_source: "environment" | "keychain" | "none" | string;
  notice: string;
  storage_notice: string;
  storage_mode: "request_scoped";
  terms_url: string;
}

export interface MacroCatalogItem {
  provider: "fred";
  series_id: string;
  title: string;
  title_zh: string;
  topic: string;
  units: string;
  frequency: string;
  source_url: string;
  cached: boolean;
  storage_mode?: "request_scoped";
  last_updated?: string | null;
}

export interface MacroObservation {
  date: string;
  value: number | null;
  realtime_start?: string | null;
  realtime_end?: string | null;
  fetched_at?: string;
}

export interface MacroSeriesDetail extends MacroCatalogItem {
  seasonal_adjustment?: string;
  notes?: string;
  source_organization?: string;
  original_source_url?: string;
  release_name?: string;
  release_url?: string;
  license?: string;
  attribution?: string;
  terms_url?: string;
  fetched_at?: string;
  storage_mode?: "request_scoped";
  observation_units?: string;
}

export interface MacroSeriesData {
  series: MacroSeriesDetail;
  observations: MacroObservation[];
}

export interface MacroChartData {
  dates: string[];
  series: Array<CurveSeries & {
    key: string;
    units?: string;
    frequency?: string;
    attribution?: string;
    source_url?: string;
    source_organization?: string;
    original_source_url?: string;
    last_updated?: string | null;
    fetched_at?: string;
    realtime_start?: Array<string | null>;
    realtime_end?: Array<string | null>;
  }>;
  transform: "level" | "change" | "yoy" | "normalize" | "zscore";
  years: number;
  transform_source: string;
  storage_mode: "request_scoped";
  terms_url: string;
}

export interface SovereignCountry {
  country_code: string;
  iso2_code?: string;
  name: string;
  name_zh: string;
  region_id?: string;
  region_name?: string;
  income_level_id?: string;
  income_level_name?: string;
  capital_city?: string;
}

export interface SovereignIndicator {
  indicator_id: string;
  name: string;
  title_zh: string;
  topic: string;
  unit: string;
  source_name?: string;
  source_note?: string;
  source_organization?: string;
  source_url: string;
  license?: string;
  license_url?: string;
  attribution?: string;
  last_updated?: string | null;
}

export interface SovereignCatalog {
  countries: SovereignCountry[];
  indicators: SovereignIndicator[];
  views: Array<{ id: "level" | "change" | "rank" | "zscore"; label: string }>;
  source: string;
  source_url: string;
  license: string;
  license_url: string;
  attribution: string;
  cache_policy: string;
}

export interface SovereignComparison {
  indicator: SovereignIndicator;
  countries: SovereignCountry[];
  years: string[];
  series: Array<CurveSeries & {
    key: string;
    raw_values: Array<number | null>;
  }>;
  view: "level" | "change" | "rank" | "zscore";
  latest_available_year?: number | null;
  latest_comparable_year?: number | null;
  summary_year?: number | null;
  latest_rows: Array<{
    country_code: string;
    country_name: string;
    value?: number | null;
    display_value?: number | null;
    rank?: number | null;
  }>;
  coverage: {
    available: number;
    total: number;
    ratio: number;
    by_country: Record<string, { available: number; total: number }>;
  };
  source: string;
  source_url: string;
  license: string;
  license_url: string;
  attribution: string;
  storage_mode: "persistent_cache";
  comparison_notice: string;
}

export interface ResearchOverview {
  projects: {
    total: number;
    active: number;
    with_conclusion: number;
    evidence: number;
    due: number;
    recent: ResearchProject[];
  };
  topics: {
    total: number;
    active: number;
    review: number;
    recent: ResearchTopic[];
  };
  evidence_basket: {
    total: number;
    oldest?: string | null;
  };
  watchlist: {
    total: number;
    macro: number;
    securities: number;
    pinned: number;
  };
  fred: FredIntegrationStatus;
  macro_cache: {
    series: number;
    points: number;
    oldest?: string | null;
    newest?: string | null;
  };
  world_bank: {
    countries: number;
    indicators: number;
    points: number;
    oldest?: number | null;
    newest?: number | null;
    last_fetched_at?: string | null;
  };
}

export interface SearchResult {
  object_type: "bond" | "future" | "convertible" | "macro" | "fx" | "topic";
  object_id: string;
  name: string;
  subtitle: string;
  page: "bonds" | "futures" | "convertibles" | "macro" | "sovereign" | "fx" | "topics";
  updated_at: string;
}

export interface AlertItem {
  id: number;
  object_type: "bond" | "future" | "convertible";
  object_id: string;
  name: string;
  metric: string;
  operator: ">" | ">=" | "<" | "<=";
  threshold: number;
  cooldown_minutes: number;
  max_triggers_per_day: number;
  quiet_start?: string | null;
  quiet_end?: string | null;
  enabled: boolean;
  created_at: string;
  last_matched?: boolean | null;
  last_value?: number | null;
  last_evaluated_at?: string | null;
}

export interface AlertTriggerItem {
  id: number;
  alert_id: number;
  object_type: string;
  object_id: string;
  name: string;
  metric: string;
  operator: string;
  threshold: number;
  trigger_value: number;
  source: string;
  observation_time?: string | null;
  triggered_at: string;
  read: boolean;
}

export interface CashFlow {
  date: string;
  years: number;
  amount: number;
  present_value: number;
}

export interface CalculatorResult {
  accrued_interest: number;
  dirty_price: number;
  ytm_pct: number;
  macaulay_duration: number;
  modified_duration: number;
  convexity: number;
  dv01: number;
  scenario_prices: Record<string, number>;
  cash_flows: CashFlow[];
  methodology: string;
}

export interface DailyReport {
  generated_at: string;
  report_date: string;
  report_mode: "intraday" | "close" | "latest";
  market_status: string;
  headline: string;
  funding: {
    tone: string;
    average_change_bp: number | null;
    items: RateItem[];
  };
  curve: {
    tenors: Record<string, number | null>;
    spreads_bp: Record<string, number | null>;
    ten_year_change_bp: number | null;
  };
  futures: TreasuryFuture[];
  bond_movers: SpotBond[];
  active_bonds: SpotBond[];
  events: MarketEvent[];
  event_groups: {
    upcoming: MarketEvent[];
    recent: MarketEvent[];
  };
  confidence: {
    level: "high" | "medium" | "low";
    score: number;
    message: string;
    trusted_sources: number;
    suspicious_rows: number;
    source_breakdown?: Array<{
      adapter: string;
      label: string;
      weight: number;
      state: HealthItem["state"];
      trust_level: HealthItem["trust_level"];
      contribution: number;
    }>;
  };
  data_health: {
    healthy: number;
    cached: number;
    available: number;
    total: number;
    history: {
      points: number;
      adapters: number;
      oldest: string | null;
      newest: string | null;
    };
  };
  research_workflow?: {
    active_projects: number;
    due_projects: number;
    macro_watchlist: number;
    pinned_watchlist: number;
    macro_cache: {
      series: number;
      points: number;
      oldest?: string | null;
      newest?: string | null;
    };
    recent_projects: Array<{
      id: number;
      title: string;
      status: ResearchStatus;
      confidence: number;
      next_review_date?: string | null;
      updated_at: string;
    }>;
  };
  data_notes: string[];
}

export interface DailyReportArchiveItem {
  report_date: string;
  report_mode: "intraday" | "close" | "latest";
  confidence_level: "high" | "medium" | "low";
  updated_at: string;
}
