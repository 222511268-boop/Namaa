import type {
  ObservedCondition,
  PlantingCategory,
  Role,
  SignalOutcome,
  SignalStatus,
  SiteType,
  TaskPriority,
  TaskStatus,
} from "./types";

export const ROLE_LABEL: Record<Role, string> = {
  admin: "Administrator",
  manager: "Green-space manager",
  inspector: "Field inspector",
  viewer: "Viewer",
};

export const SITE_TYPE_LABEL: Record<SiteType, string> = {
  park: "Park",
  garden: "Public garden",
  median: "Roadside / median",
  plaza: "Plaza",
  other: "Other",
};

export const PLANTING_LABEL: Record<PlantingCategory, string> = {
  turf: "Turf / lawn",
  shrubs: "Shrubs and groundcover",
  trees: "Trees",
  native: "Native / drought-adapted",
  mixed: "Mixed planting",
  unknown: "Not yet recorded",
};

export function formatArea(m2: number): string {
  if (m2 >= 10_000) return `${(m2 / 10_000).toLocaleString("en-GB", { maximumFractionDigits: 2 })} ha`;
  return `${Math.round(m2).toLocaleString("en-GB")} m²`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Riyadh",
  });
}

export function formatIndex(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : v.toFixed(2);
}

export function percent(v: number): string {
  return `${Math.round(v * 100)}%`;
}

export const SIGNAL_STATUS_LABEL: Record<SignalStatus, string> = {
  open: "Open",
  under_inspection: "Under inspection",
  dismissed: "Dismissed",
  closed: "Closed",
};

export const OUTCOME_LABEL: Record<SignalOutcome, string> = {
  confirmed: "Confirmed",
  not_confirmed: "Not confirmed",
  inconclusive: "Inconclusive",
};

export const TASK_STATUS_LABEL: Record<TaskStatus, string> = {
  assigned: "Assigned",
  in_progress: "In progress",
  completed: "Completed",
  cancelled: "Cancelled",
};

export const PRIORITY_LABEL: Record<TaskPriority, string> = { high: "High", medium: "Medium", low: "Low" };

export const CONDITION_LABEL: Record<ObservedCondition, string> = {
  healthy: "Healthy",
  stressed: "Stressed (dry, yellowing, thinning)",
  damaged: "Damaged (broken, vandalised, pest)",
  dead_or_missing: "Dead or missing",
  not_vegetation: "Not vegetation (works, paving, replanting)",
};

export const FACTOR_LABEL: Record<string, string> = {
  severity: "Severity",
  persistence: "Persistence",
  size: "Site size",
  site_type: "Site type",
  heat: "Surface heat",
};

export function signed(v: number, digits = 2): string {
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(digits)}`;
}

/** UTC calendar date n days ago (YYYY-MM-DD), matching the server's date checks for processing ranges. */
export function utcIsoDaysAgo(days: number): string {
  return new Date(Date.now() - days * 86400e3).toISOString().slice(0, 10);
}

export function todayIso(offsetDays = 0): string {
  const d = new Date(Date.now() + offsetDays * 86400e3);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60e3).toISOString().slice(0, 10);
}

/** Imported parks without a name are stored as "Unnamed park (OSM way 123)": show the reference separately. */
export function splitSiteName(name: string): { title: string; ref: string | null } {
  const m = /^(Unnamed [^(]+?) \((OSM (?:way|relation|node) \d+)\)$/.exec(name);
  return m ? { title: m[1], ref: m[2] } : { title: name, ref: null };
}
