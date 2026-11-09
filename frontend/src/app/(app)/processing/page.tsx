"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { RequireRole } from "@/components/app-shell";
import { RunStatusBadge } from "@/components/run-status";
import { Alert, Button, Card, EmptyState, Field, Icon, inputClass, PageHeader, Segmented, Skeleton } from "@/components/ui";
import { api, ApiError, errorMessage } from "@/lib/api";
import { formatDate, formatDateTime, utcIsoDaysAgo as daysAgo } from "@/lib/format";
import { isActive, lastUsedRange, rerun, runProgress, smartRange, startRun, useRuns } from "@/lib/live-runs";
import { can } from "@/lib/permissions";
import type { DataFreshness, ProcessingRun, WorkspaceSummary } from "@/lib/types";
import { useUser } from "@/components/session";

type Kind = "sentinel2" | "landsat_lst" | "weather";
const KIND_LABEL: Record<ProcessingRun["kind"], string> = {
  sentinel2: "Sentinel-2 vegetation",
  landsat_lst: "Landsat surface temperature",
  weather: "Weather (Open-Meteo)",
  osm_import: "OpenStreetMap import",
};
const KIND_HINT: Record<Kind, string> = {
  sentinel2: "Vegetation indices (NDVI, NDMI) for every active green space, then baselines and signals.",
  landsat_lst: "Land surface temperature for the pilot area: the map layer and each site's value. Signals are re-scored with heat.",
  weather: "Daily reference evapotranspiration for water-demand estimates. Also updated automatically once a day.",
};

function describe(run: ProcessingRun): string {
  const p = run.params as Record<string, string | number | null>;
  if (run.kind === "osm_import") return `${KIND_LABEL.osm_import} · ${p.district ?? "district"}`;
  const scope = run.kind === "landsat_lst" ? " · pilot area" : p.site_ids ? " · selected sites" : " · all active sites";
  return `${KIND_LABEL[run.kind]} · ${p.start_date} to ${p.end_date}${scope}`;
}

function counts(r: ProcessingRun): string {
  if (r.kind === "osm_import") return ` · ${r.items_written} sites added`;
  if (r.kind === "weather") return ` · ${r.scenes_processed}/${r.scenes_found} sites · ${r.items_written} daily values written`;
  const unit = r.kind === "landsat_lst" ? "site values" : "observations";
  return ` · ${r.scenes_processed}/${r.scenes_found} scenes · ${r.items_written} ${unit} written · ${r.items_skipped} unchanged`;
}

/** Latest data date from each source and the run that last updated it (US23). */
function Freshness({ version }: { version: number }) {
  const [rows, setRows] = useState<DataFreshness[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<DataFreshness[]>("/api/data-freshness").then(setRows).catch((e) => setError(errorMessage(e)));
  }, [version]);
  return (
    <Card title="Data freshness" className="mb-6">
      {error && <div className="p-5"><Alert>{error}</Alert></div>}
      {!rows && !error && <div className="p-5" aria-hidden="true"><Skeleton className="h-16" /></div>}
      {rows && (
        <dl className="grid gap-px overflow-hidden rounded-b-lg bg-line sm:grid-cols-2 lg:grid-cols-4" data-testid="freshness">
          {rows.map((f) => (
            <div key={f.source} className="bg-surface px-5 py-4">
              <dt className="text-cap text-muted">{f.label}</dt>
              <dd className="num mt-0.5 text-lg font-medium text-ink">{f.latest_data_on ? formatDate(f.latest_data_on) : "No data yet"}</dd>
              <dd className="mt-1 flex flex-wrap items-center gap-1.5 text-cap text-muted">
                {f.last_run ? <><RunStatusBadge status={f.last_run.status} /> last run {formatDateTime(f.last_run.created_at)}</> : "Never run"}
              </dd>
              <dd className="mt-0.5 text-cap text-muted">{f.provider}</dd>
            </div>
          ))}
        </dl>
      )}
    </Card>
  );
}

type Preset = "since" | "last" | "30" | "90" | "custom";

export default function ProcessingPage() {
  const runs = useRuns(true); // live: refreshes while a run is queued or running
  const user = useUser();
  const [kind, setKind] = useState<Kind>("sentinel2");
  const [rerunning, setRerunning] = useState<string | null>(null);
  const [rerunError, setRerunError] = useState<string | null>(null);
  const activeCount = runs?.filter(isActive).length ?? 0;
  const [latestObs, setLatestObs] = useState<string | null | undefined>(undefined);
  const [preset, setPreset] = useState<Preset>("since");
  const [start, setStart] = useState(daysAgo(90));
  const [end, setEnd] = useState(daysAgo(1));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const last = lastUsedRange();
  const touched = useRef(false); // the user changed the dates: never overwrite them with a default

  // Smart default: everything since the newest stored image.
  useEffect(() => {
    api<WorkspaceSummary>("/api/summary")
      .then((s) => {
        setLatestObs(s.latest_observation_on);
        if (touched.current) return;
        const r = smartRange(s.latest_observation_on);
        setStart(r.start);
        setEnd(r.end);
      })
      .catch(() => setLatestObs(null));
  }, []);

  function choose(p: Preset) {
    touched.current = true;
    setPreset(p);
    const r =
      p === "since" ? smartRange(latestObs) :
      p === "last" && last ? last :
      p === "30" ? { start: daysAgo(30), end: daysAgo(1) } :
      p === "90" ? { start: daysAgo(90), end: daysAgo(1) } : null;
    if (r) {
      setStart(r.start);
      setEnd(r.end);
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErrors({});
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      await startRun({ start, end }, undefined, kind);
      setNotice("Run queued. It is processed in the background; progress updates live here and in the sidebar.");
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fieldErrors).length) setErrors(err.fieldErrors);
      else setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function doRerun(r: ProcessingRun) {
    setRerunError(null);
    setRerunning(r.id);
    try {
      await rerun(r.id);
    } catch (err) {
      setRerunError(errorMessage(err));
    } finally {
      setRerunning(null);
    }
  }

  const presets: { value: Preset; label: string }[] = [
    { value: "since", label: "Since last update" },
    ...(last ? [{ value: "last" as const, label: "Last used" }] : []),
    { value: "30", label: "30 days" },
    { value: "90", label: "90 days" },
    { value: "custom", label: "Custom" },
  ];

  return (
    <RequireRole allowed={can.runProcessing}>
      <div className="mx-auto max-w-content px-4 py-6 sm:px-6 sm:py-8">
        <PageHeader title="Satellite data" subtitle="Bring vegetation, surface temperature and weather data up to date, and check how fresh each source is." />
        <Freshness version={activeCount} />
        <Card title="Start a processing run">
          <form onSubmit={submit} noValidate className="space-y-4 p-5">
            <div className="overflow-x-auto">
              <Segmented<Kind> label="Data type" value={kind} onChange={setKind} size="md" options={[
                { value: "sentinel2", label: "Vegetation" },
                { value: "landsat_lst", label: "Surface heat" },
                { value: "weather", label: "Weather" },
              ]} />
            </div>
            <p className="text-sm text-muted">{KIND_HINT[kind]}</p>
            <div className="overflow-x-auto">
              <Segmented label="Date range" value={preset} onChange={choose} size="md" options={presets} />
            </div>
            <div className="flex flex-wrap items-end gap-4">
              <Field label="From" htmlFor="start" error={errors.start_date}>
                <input id="start" type="date" value={start} max={end} disabled={latestObs === undefined} onInput={(e) => { touched.current = true; setStart(e.currentTarget.value); setPreset("custom"); }}
                  className={inputClass(!!errors.start_date)} />
              </Field>
              <Field label="To" htmlFor="end" error={errors.end_date}>
                <input id="end" type="date" value={end} max={daysAgo(0)} disabled={latestObs === undefined} onInput={(e) => { touched.current = true; setEnd(e.currentTarget.value); setPreset("custom"); }}
                  className={inputClass(!!errors.end_date)} />
              </Field>
              <Button type="submit" busy={busy}>Start run</Button>
            </div>
            <p className="text-cap text-muted">Repeating a range never duplicates observations; only pixels inside registered boundaries are read.</p>
            {errors.site_ids && <Alert>{errors.site_ids}</Alert>}
            {error && <Alert>{error}</Alert>}
            {notice && <Alert tone="success">{notice}</Alert>}
          </form>
        </Card>

        <Card title="Recent runs" className="mt-6" action={runs?.some(isActive) ? <span className="flex items-center gap-2 text-cap text-primary-ink"><span className="h-2 w-2 animate-live rounded-full bg-primary" aria-hidden="true" />Live</span> : undefined}>
          {!runs && <div className="space-y-2 p-5" aria-hidden="true"><Skeleton className="h-10" /><Skeleton className="h-10" /></div>}
          {rerunError && <div className="px-5 pt-3"><Alert>{rerunError}</Alert></div>}
          {runs && runs.length === 0 && <EmptyState icon="satellite" title="No runs yet">Start a run above to retrieve satellite observations.</EmptyState>}
          {runs && runs.length > 0 && (
            <ul className="mt-2 divide-y divide-line" data-testid="run-list">
              {(showAll ? runs : runs.slice(0, 6)).map((r) => {
                const progress = isActive(r) ? runProgress(r) : null;
                return (
                  <li key={r.id} className="px-5 py-3.5 text-sm">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="font-medium text-ink">{describe(r)}</p>
                      <RunStatusBadge status={r.status} />
                    </div>
                    {progress !== null && (
                      <div className="mt-2 h-1 overflow-hidden rounded-full bg-surface-2" aria-hidden="true">
                        <div className="h-full origin-left rounded-full bg-primary transition-transform duration-slow" style={{ transform: `scaleX(${progress})` }} />
                      </div>
                    )}
                    <p className="mt-1 text-cap text-muted">
                      {formatDateTime(r.created_at)}{r.requested_by_name ? ` · ${r.requested_by_name}` : ""}
                      {r.requested_by_name ? "" : " · automatic"}
                      {counts(r)}
                    </p>
                    {r.error && <p className="mt-1 text-cap text-danger-ink">{r.error}</p>}
                    {r.kind !== "osm_import" && !isActive(r) && (user.role === "admin" || r.status === "failed") && (
                      <Button size="sm" variant="secondary" className="mt-2" busy={rerunning === r.id} onClick={() => void doRerun(r)}>
                        <Icon name="refresh" className="h-4 w-4" /> Re-run
                      </Button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          {runs && runs.length > 6 && (
            <div className="border-t border-line px-5 py-2.5">
              <button type="button" onClick={() => setShowAll((v) => !v)} aria-expanded={showAll}
                className="min-h-9 text-sm font-medium text-primary-ink hover:underline">
                {showAll ? "Show fewer runs" : `Show all ${runs.length} runs`}
              </button>
            </div>
          )}
        </Card>
      </div>
    </RequireRole>
  );
}
