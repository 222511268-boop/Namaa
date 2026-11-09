export type Role = "admin" | "manager" | "inspector" | "viewer";
export type SiteType = "park" | "garden" | "median" | "plaza" | "other";
export type PlantingCategory = "turf" | "shrubs" | "trees" | "native" | "mixed" | "unknown";
export type RunStatus = "queued" | "running" | "succeeded" | "failed";
export type RunKind = "sentinel2" | "osm_import" | "landsat_lst" | "weather";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
}

export interface District {
  id: number;
  name_en: string | null;
  name_ar: string | null;
  site_count: number;
}

export interface LatestObservation {
  acquired_on: string;
  ndvi_mean: number | null;
  ndmi_mean: number | null;
}

export interface SiteSummary {
  id: string;
  name: string;
  name_ar: string | null;
  site_type: SiteType;
  planting_category: PlantingCategory;
  district_id: number | null;
  district_name: string | null;
  area_m2: number;
  low_confidence: boolean;
  needs_review: boolean;
  status: "active" | "inactive";
  source: "osm" | "manual";
  latest: LatestObservation | null;
}

export interface SiteDetail extends SiteSummary {
  irrigated_area_m2: number | null;
  source_ref: string | null;
  notes: string | null;
  geometry: GeoJSON.MultiPolygon | GeoJSON.Polygon;
  created_at: string;
  updated_at: string;
  source_attribution: string | null;
}

export interface Observation {
  acquired_on: string;
  acquired_at: string;
  scene_id: string;
  platform: string;
  ndvi_mean: number | null;
  ndvi_std: number | null;
  ndmi_mean: number | null;
  ndmi_std: number | null;
  valid_pixels: number;
  total_pixels: number;
  valid_share: number;
  usable: boolean;
}

export interface ConditionHistory {
  site_id: string;
  observations: Observation[];
  usable_count: number;
  unusable_count: number;
  latest_usable_on: string | null;
  attribution: string | null;
  thresholds: { min_valid_share: number; min_valid_pixels: number };
}

export interface ProcessingRun {
  id: string;
  kind: RunKind;
  status: RunStatus;
  params: Record<string, unknown>;
  requested_by_name: string | null;
  scenes_found: number;
  scenes_processed: number;
  items_written: number;
  items_skipped: number;
  error: string | null;
  messages: unknown[];
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface ImportResult {
  run_id: string;
  district: string;
  features_found: number;
  created: number;
  already_imported: number;
  skipped: { osm_ref: string; name: string | null; reason: string }[];
  created_site_ids: string[];
}

export interface WorkspaceSummary {
  role: Role;
  sites: {
    active: number;
    needs_review: number;
    low_confidence: number;
    with_observations: number;
    total_area_m2: number;
  };
  latest_observation_on: string | null;
  latest_run?: ProcessingRun | null;
  signals?: { open: number; under_inspection: number };
  tasks?: { open: number; overdue: number };
}

// ---------------------------------------------------------------- Sprint 2

export type SignalStatus = "open" | "under_inspection" | "dismissed" | "closed";
export type SignalOutcome = "confirmed" | "not_confirmed" | "inconclusive";
export type TaskType = "inspection" | "maintenance";
export type TaskPriority = "high" | "medium" | "low";
export type TaskStatus = "assigned" | "in_progress" | "completed" | "cancelled";
export type ObservedCondition = "healthy" | "stressed" | "damaged" | "dead_or_missing" | "not_vegetation";

export interface PriorityFactors {
  severity: number;
  persistence: number;
  size: number;
  site_type: number;
  /** Sprint 3: heat points (null when the site has no recent surface temperature data). */
  heat?: number | null;
  heat_c?: number;
  heat_date?: string;
  heat_percentile?: number;
  heat_sites_compared?: number;
  mean_z?: number;
  run_length?: number;
}

export interface SignalSummary {
  id: string;
  site_id: string;
  site_name: string;
  site_name_ar: string | null;
  district_id: number | null;
  district_name: string | null;
  site_type: string;
  area_m2: number;
  status: SignalStatus;
  outcome: SignalOutcome | null;
  detected_at: string;
  first_obs_on: string;
  last_obs_on: string;
  latest_ndvi: number;
  baseline_median: number;
  deviation: number;
  z_score: number;
  priority_score: number;
  priority_factors: PriorityFactors;
  reopened_count: number;
}

export interface EvidenceObservation {
  observation_id: string;
  date: string;
  scene_id: string;
  ndvi: number;
  baseline_median: number;
  baseline_sd: number;
  deviation: number;
  z: number;
}

export interface EvidenceImage {
  date: string;
  scene_id: string;
  ndvi: number | null;
  url: string | null;
}

export interface Decision {
  decision: string;
  reason: string | null;
  outcome: SignalOutcome | null;
  user_name: string | null;
  created_at: string;
}

export interface Photo {
  id: string;
  url: string;
  thumb_url: string;
  width: number;
  height: number;
}

export interface Finding {
  visit_date: string | null;
  condition: ObservedCondition | null;
  notes: string | null;
  recorded_at: string | null;
  photos: Photo[];
}

export interface Task {
  id: string;
  site_id: string;
  site_name: string;
  site_name_ar: string | null;
  district_name: string | null;
  signal_id: string | null;
  task_type: TaskType;
  title: string;
  instructions: string | null;
  priority: TaskPriority;
  due_date: string;
  overdue: boolean;
  assignee_id: string;
  assignee_name: string;
  status: TaskStatus;
  created_by_name: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  finding: Finding | null;
}

export interface SignalDetail extends SignalSummary {
  boundary_changed: boolean;
  outcome_method: string | null;
  closed_at: string | null;
  baseline_sd: number;
  evidence: { rule?: { window: number; z_threshold: number; min_drop: number }; observations?: EvidenceObservation[] };
  before_image: EvidenceImage | null;
  after_image: EvidenceImage | null;
  decisions: Decision[];
  tasks: Task[];
  attribution: string;
}

export interface Baseline {
  month: number;
  target_year: number;
  n_obs: number;
  median_ndvi: number | null;
  robust_sd: number | null;
  p10: number | null;
  p90: number | null;
  years: string;
  available: boolean;
}

export interface TimelineEvent {
  at: string;
  kind: string;
  text: string;
  detail?: string | null;
  user: string | null;
  signal_id?: string | null;
  task_id?: string | null;
}

export interface Inspector {
  id: string;
  full_name: string;
  email: string;
}

// ---------------------------------------------------------------- Sprint 3

export interface WaterDay {
  day: string;
  et0_mm: number | null;
  tmax_c: number | null;
  precip_mm: number | null;
  demand_l: number | null;
  scheduled_l: number | null;
}

export interface WaterEstimate {
  label: string;
  formula: string;
  inputs: {
    plant_category: PlantingCategory;
    plant_factor: number;
    plant_factor_note: string;
    irrigated_area_m2: number;
    irrigated_area_source: string;
    location: [number, number];
    rainfall: string;
  };
  source: string;
  period: { start: string; end: string; days: number; days_with_data: number };
  totals: { demand_m3: number; et0_mm: number; precip_mm: number; mean_daily_demand_m3: number | null };
  daily: WaterDay[];
  has_schedule: boolean;
  comparison: {
    days_compared: number;
    scheduled_m3: number;
    demand_m3: number;
    difference_m3: number;
    difference_pct: number | null;
    label: string;
  } | null;
  latest_weather_on: string | null;
  weather_fetched_at: string | null;
  notice: string | null;
}

export interface Schedule {
  id: string;
  site_id: string;
  start_date: string;
  end_date: string | null;
  weekdays: number[];
  litres_per_day: number;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlantFactor {
  category: PlantingCategory;
  factor: number;
  source_note: string;
  updated_at: string;
}

export interface HeatLayer {
  id: string;
  scene_id: string;
  platform: string;
  acquired_on: string;
  url: string;
  bounds: [number, number, number, number];
  min_c: number;
  max_c: number;
  valid_share: number;
}

export interface HeatLayers {
  layers: HeatLayer[];
  ramp: { c: number; color: string }[];
  unit: string;
  resolution: string;
  attribution: string;
}

export interface SiteHeat {
  latest: {
    acquired_on: string;
    platform: string;
    scene_id: string;
    site_c: number | null;
    surround_c: number | null;
    difference_c: number | null;
    valid_share: number;
  } | null;
  history: { acquired_on: string; site_c: number | null; surround_c: number | null; usable: boolean }[];
  priority_heat: { surround_c: number; acquired_on: string; percentile: number; sites_compared: number } | null;
  surround_m: number;
  resolution: string;
  attribution: string;
  method: string;
}

export type ConditionKey = "needs_attention" | "within_range" | "below_range" | "baseline_unavailable" | "no_satellite_data" | "low_confidence";

export interface Overview {
  filters: { district_id: number | null; district_name: string | null; start: string; end: string };
  generated_at: string;
  sites_total: number;
  conditions: Record<ConditionKey, number>;
  condition_labels: Record<ConditionKey, string>;
  signals: Record<SignalStatus, number>;
  signals_total: number;
  tasks: Record<TaskStatus, number>;
  tasks_total: number;
  overdue_tasks: number;
  outcomes: Record<SignalOutcome, number>;
  outcomes_by_method: { field_inspection: number; desk_review: number };
  confirmation_rate_pct: number | null;
  definitions: Record<string, string>;
}

export interface Evidence {
  text: string;
  fact_ids: string[];
}

export interface Fact {
  id: string;
  label: string;
  value: string | number;
  unit?: string;
}

export interface SignalBriefContent {
  headline: string;
  summary: Evidence;
  explanations: {
    title: string;
    assessment: "more likely" | "possible" | "less likely";
    supporting: Evidence[];
    contradicting: Evidence[];
  }[];
  checklist: Evidence[];
  data_gaps: string[];
}

export interface OverviewSummaryContent {
  headline: string;
  paragraphs: Evidence[];
  watch_items: Evidence[];
}

export interface AiBrief<C> {
  id: string;
  kind: "signal_brief" | "overview_summary";
  content: C;
  facts: Fact[];
  model: string;
  prompt_version: string;
  created_at: string;
  reused: boolean;
  outdated: boolean;
  label: string;
  checklist_text?: string;
  filters?: Overview["filters"];
}

export interface AiStatus {
  enabled: boolean;
  model: string | null;
  daily_limit: number;
  used_today: number;
  label: string;
}

export interface ActivityEvent {
  id: number;
  at: string;
  user_id: string | null;
  user_name: string | null;
  user_role: Role | null;
  action: string;
  action_label: string;
  entity_type: string | null;
  entity_id: string | null;
  summary: string;
  details: Record<string, unknown>;
}

export interface DataFreshness {
  source: RunKind;
  label: string;
  provider: string;
  latest_data_on: string | null;
  last_run: { id: string; status: RunStatus; created_at: string; finished_at: string | null; error: string | null } | null;
}
