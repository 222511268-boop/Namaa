"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, ApiError, errorMessage } from "@/lib/api";
import { formatArea, formatDate, PLANTING_LABEL } from "@/lib/format";
import type { Schedule, WaterEstimate } from "@/lib/types";
import { Alert, Badge, Button, Card, Field, Icon, inputClass, Segmented, Skeleton, cx } from "./ui";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const m3 = (v: number) => `${v.toLocaleString("en-GB", { maximumFractionDigits: 1 })} m³`;
const litres = (v: number) => `${Math.round(v).toLocaleString("en-GB")} L`;

function shiftIso(iso: string, days: number) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** Daily estimated demand (bars) with the user-entered schedule (line) when one exists. One axis: litres. */
function DemandChart({ w }: { w: WaterEstimate }) {
  const days = w.daily.filter((d) => d.demand_l !== null);
  if (days.length < 2) return null;
  const max = Math.max(...days.map((d) => Math.max(d.demand_l ?? 0, d.scheduled_l ?? 0)), 1);
  const W = 600, H = 120, gap = 2;
  const bw = W / days.length;
  const y = (v: number) => H - (v / max) * (H - 4);
  let previousScheduled = false;
  const sched = w.has_schedule ? days.map((d, i) => {
    if (d.scheduled_l === null) { previousScheduled = false; return ""; }
    const segment = `${previousScheduled ? "L" : "M"}${i * bw + bw / 2},${y(d.scheduled_l)}`;
    previousScheduled = true;
    return segment;
  }).join(" ") : "";
  return (
    <figure className="mt-4">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-32 w-full" preserveAspectRatio="none" role="img"
        aria-label={`Daily estimated water demand from ${w.period.start} to ${w.period.end}; values are listed in the table below.`}>
        <line x1="0" x2={W} y1={H - 0.5} y2={H - 0.5} stroke="var(--c-line)" />
        {days.map((d, i) => (
          <rect key={d.day} x={i * bw + gap / 2} y={y(d.demand_l!)} width={Math.max(bw - gap, 1)} height={H - y(d.demand_l!)}
            rx="2" fill="var(--c-factor-1)">
            <title>{`${d.day}: estimated ${litres(d.demand_l!)}${d.scheduled_l !== null ? ` · scheduled ${litres(d.scheduled_l)}` : ""}`}</title>
          </rect>
        ))}
        {sched && <path d={sched} fill="none" stroke="var(--c-factor-2)" strokeWidth="2" vectorEffect="non-scaling-stroke" />}
      </svg>
      <figcaption className="mt-1 flex flex-wrap gap-x-4 text-cap text-muted">
        <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-[var(--c-factor-1)]" />Estimated demand per day</span>
        {w.has_schedule && <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-3 bg-[var(--c-factor-2)]" />Scheduled (user-entered)</span>}
        <span>Peak {litres(max)}</span>
      </figcaption>
      <details className="mt-2 text-cap">
        <summary className="cursor-pointer text-muted hover:text-ink">Daily values</summary>
        <div className="mt-1 max-h-56 overflow-y-auto">
          <table className="w-full text-left">
            <thead className="text-muted"><tr><th className="py-1 font-medium">Day</th><th className="font-medium">ET0 (mm)</th><th className="font-medium">Estimate (L)</th>{w.has_schedule && <th className="font-medium">Scheduled (L)</th>}</tr></thead>
            <tbody className="num text-ink-2">
              {w.daily.map((d) => (
                <tr key={d.day} className="border-t border-line">
                  <td className="py-1">{d.day}</td><td>{d.et0_mm ?? "–"}</td><td>{d.demand_l?.toLocaleString("en-GB") ?? "–"}</td>
                  {w.has_schedule && <td>{d.scheduled_l?.toLocaleString("en-GB") ?? "–"}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}

function Comparison({ c }: { c: NonNullable<WaterEstimate["comparison"]> }) {
  if (!c.days_compared) return <p className="text-sm text-muted">No days in this period have both stored ET0 and a schedule.</p>;
  const pct = c.difference_pct;
  const over = c.difference_m3 > 0;
  return (
    <div className="rounded-md bg-surface-2 p-3" data-testid="water-comparison">
      <p className="text-sm text-ink">
        Over {c.days_compared} scheduled days the schedule applies <strong className="num">{m3(c.scheduled_m3)}</strong> against an
        estimated demand of <strong className="num">{m3(c.demand_m3)}</strong>:
      </p>
      <p className={cx("num mt-1 text-lg font-medium", Math.abs(pct ?? 0) >= 25 ? "text-signal-ink" : "text-ink")}>
        {over ? "+" : c.difference_m3 < 0 ? "−" : ""}{m3(Math.abs(c.difference_m3))}
        {pct !== null && <span className="text-sm font-normal text-muted"> ({over ? "+" : pct < 0 ? "−" : ""}{Math.abs(pct)}% {over ? "above" : "below"} estimate)</span>}
      </p>
      <p className="mt-1 text-cap text-muted">{c.label} Demand is an estimate; differences suggest possible over- or under-watering to check, not a finding.</p>
    </div>
  );
}

type Draft = { start: string; end: string; weekdays: number[]; litres: string; notes: string };
const emptyDraft = (): Draft => ({ start: new Date().toISOString().slice(0, 10), end: "", weekdays: [], litres: "", notes: "" });

function FactorForm({ w, onSaved }: { w: WaterEstimate; onSaved: () => void }) {
  const [factor, setFactor] = useState(String(w.inputs.plant_factor));
  const [note, setNote] = useState(w.inputs.plant_factor_note);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return <form className="mt-3 space-y-3" onSubmit={async e => {
    e.preventDefault(); setBusy(true); setError(null);
    try { await api(`/api/plant-factors/${w.inputs.plant_category}`, { method: "PUT", json: { factor: Number(factor), source_note: note } }); onSaved(); }
    catch (err) { setError(errorMessage(err)); } finally { setBusy(false); }
  }}>
    <p className="text-cap text-muted">This assumption applies to every site in the {PLANTING_LABEL[w.inputs.plant_category].toLowerCase()} category.</p>
    {error && <Alert>{error}</Alert>}
    <Field label="Plant factor" htmlFor="water-factor"><input id="water-factor" type="number" step="0.001" min="0.05" max="1.2" required value={factor} onChange={e => setFactor(e.target.value)} className={inputClass()} /></Field>
    <Field label="Source / assumption note" htmlFor="water-factor-note"><textarea id="water-factor-note" required minLength={3} maxLength={300} value={note} onChange={e => setNote(e.target.value)} className={inputClass()} /></Field>
    <Button type="submit" variant="secondary" size="sm" busy={busy}>Save category factor</Button>
  </form>;
}

function ScheduleForm({ siteId, editing, onDone }: { siteId: string; editing: Schedule | null; onDone: () => void }) {
  const [d, setD] = useState<Draft>(() =>
    editing
      ? { start: editing.start_date, end: editing.end_date ?? "", weekdays: editing.weekdays, litres: String(editing.litres_per_day), notes: editing.notes ?? "" }
      : emptyDraft(),
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const toggle = (n: number) => setD({ ...d, weekdays: d.weekdays.includes(n) ? d.weekdays.filter((x) => x !== n) : [...d.weekdays, n].sort() });

  async function save(e: FormEvent) {
    e.preventDefault();
    const local: Record<string, string> = {};
    if (!d.weekdays.length) local.weekdays = "Choose at least one watering day.";
    if (!(Number(d.litres) > 0)) local.litres_per_day = "Enter the litres applied on each watering day.";
    setErrors(local);
    if (Object.keys(local).length) return;
    setBusy(true);
    const body = { start_date: d.start, end_date: d.end || null, weekdays: d.weekdays, litres_per_day: Number(d.litres), notes: d.notes || null };
    try {
      await api(editing ? `/api/schedules/${editing.id}` : `/api/sites/${siteId}/schedules`, { method: editing ? "PUT" : "POST", json: body });
      onDone();
    } catch (err) {
      setErrors(err instanceof ApiError && Object.keys(err.fieldErrors).length ? err.fieldErrors : { form: errorMessage(err) });
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} noValidate className="space-y-4 rounded-md p-4 ring-1 ring-primary/30" data-testid="schedule-form">
      <p className="text-cap font-medium text-primary-ink">{editing ? "Edit schedule" : "New irrigation schedule"} · user-entered</p>
      {errors.form && <Alert>{errors.form}</Alert>}
      <div className="flex flex-wrap gap-4">
        <Field label="From" htmlFor="sch-start" error={errors.start_date}>
          <input id="sch-start" type="date" value={d.start} onInput={(e) => setD({ ...d, start: e.currentTarget.value })} className={inputClass(!!errors.start_date)} />
        </Field>
        <Field label="Until (optional)" htmlFor="sch-end" error={errors.end_date}>
          <input id="sch-end" type="date" value={d.end} min={d.start} onInput={(e) => setD({ ...d, end: e.currentTarget.value })} className={inputClass(!!errors.end_date)} />
        </Field>
        <Field label="Litres per watering day" htmlFor="sch-litres" error={errors.litres_per_day} hint="Total for the site">
          <input id="sch-litres" inputMode="decimal" value={d.litres} onChange={(e) => setD({ ...d, litres: e.target.value })} className={inputClass(!!errors.litres_per_day)} />
        </Field>
      </div>
      <fieldset>
        <legend className="mb-1.5 text-sm font-medium text-ink">Watering days</legend>
        <div className="flex flex-wrap gap-1.5">
          {DAYS.map((label, i) => (
            <label key={label} className={cx("inline-flex min-h-9 cursor-pointer items-center rounded-md px-3 text-sm ring-1 ring-inset has-focus-visible:ring-2 has-focus-visible:ring-primary",
              d.weekdays.includes(i + 1) ? "bg-primary text-on-primary ring-primary" : "bg-surface text-ink-2 ring-line-strong hover:bg-surface-2")}>
              <input type="checkbox" className="sr-only" checked={d.weekdays.includes(i + 1)} onChange={() => toggle(i + 1)} />
              {label}
            </label>
          ))}
        </div>
        {errors.weekdays && <p className="mt-1 text-cap text-danger-ink" role="alert">{errors.weekdays}</p>}
      </fieldset>
      <Field label="Notes (optional)" htmlFor="sch-notes">
        <input id="sch-notes" value={d.notes} maxLength={1000} onChange={(e) => setD({ ...d, notes: e.target.value })} className={inputClass(false)} />
      </Field>
      <div className="flex gap-2">
        <Button type="submit" busy={busy}>{editing ? "Save schedule" : "Add schedule"}</Button>
        <Button type="button" variant="ghost" onClick={onDone}>Cancel</Button>
      </div>
    </form>
  );
}

/** Water demand estimate and schedule comparison for one site (US17-US18). */
export function WaterCard({ siteId, canEdit }: { siteId: string; canEdit: boolean }) {
  const [period, setPeriod] = useState<"30" | "90" | "custom">("30");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [w, setW] = useState<WaterEstimate | null>(null);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<Schedule | "new" | null>(null);
  const [anchor, setAnchor] = useState<string | null>(null);

  const load = useCallback(() => {
    if (period === "custom" && (!customStart || !customEnd || customEnd < customStart)) return;
    const q = period === "custom" ? `?start=${customStart}&end=${customEnd}` : anchor && period === "90" ? `?start=${shiftIso(anchor, -89)}&end=${anchor}` : "";
    Promise.all([api<WaterEstimate>(`/api/sites/${siteId}/water${q}`), api<Schedule[]>(`/api/sites/${siteId}/schedules`)])
      .then(([est, sch]) => {
        setW(est);
        setError(null);
        setSchedules(sch);
        setAnchor((a) => a ?? est.period.end);
      })
      .catch((e) => setError(errorMessage(e)));
  }, [siteId, period, anchor, customStart, customEnd]);
  useEffect(load, [load]);

  async function remove(s: Schedule) {
    try {
      await api(`/api/schedules/${s.id}`, { method: "DELETE" });
      load();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <Card id="water" title={<span className="inline-flex items-center gap-2"><Icon name="drop" className="h-4 w-4 text-info-ink" /> Water demand</span>}
      action={<Badge tone="warn" title="Calculated from weather data and assumptions; not a measurement">Estimate</Badge>}>
      <div className="space-y-4 px-5 py-4" data-testid="water-card">
        {error && <Alert>{error}</Alert>}
        {!w && !error && <Skeleton className="h-32" />}
        {w && (
          <>
            {w.notice && <Alert tone="warn">{w.notice}</Alert>}
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-cap text-muted">Estimated demand, {formatDate(w.period.start)} – {formatDate(w.period.end)}</p>
                <p className="num text-2xl font-medium text-ink" data-testid="water-total">{w.period.days_with_data > 0 ? m3(w.totals.demand_m3) : "Unavailable"}</p>
                <p className="text-cap text-muted">
                  {w.totals.mean_daily_demand_m3 !== null ? `${m3(w.totals.mean_daily_demand_m3)} per day on average · ` : ""}
                  {w.period.days_with_data} of {w.period.days} days with weather data
                </p>
              </div>
              <Segmented label="Period" value={period} onChange={setPeriod} options={[{ value: "30", label: "30 days" }, { value: "90", label: "90 days" }, { value: "custom", label: "Custom" }]} />
            </div>
            {period === "custom" && <div className="flex flex-wrap gap-3">
              <Field label="Estimate from" htmlFor="water-start"><input id="water-start" type="date" value={customStart} onInput={e => setCustomStart(e.currentTarget.value)} className={inputClass()} /></Field>
              <Field label="Estimate through" htmlFor="water-end"><input id="water-end" type="date" value={customEnd} min={customStart} onInput={e => setCustomEnd(e.currentTarget.value)} className={inputClass()} /></Field>
              {(!customStart || !customEnd || customEnd < customStart) && <p className="text-cap text-muted">Choose both dates in order to load the selected period. Values below retain their displayed date range.</p>}
            </div>}
            <DemandChart w={w} />
            {w.comparison ? <Comparison c={w.comparison} /> : (
              <p className="text-sm text-muted" data-testid="no-schedule">{w.period.days_with_data > 0 ? "No irrigation schedule entered: estimated demand only." : "No irrigation schedule entered. A comparison also needs stored ET0 for the selected period."}</p>
            )}
            <details className="rounded-md bg-surface-2 px-4 py-3 text-sm">
              <summary className="cursor-pointer font-medium text-ink">Formula, inputs and source</summary>
              <dl className="mt-2 space-y-1.5 text-ink-2">
                <div><dt className="inline font-medium text-ink">Formula: </dt><dd className="inline" data-testid="water-formula">{w.formula}</dd></div>
                <div><dt className="inline font-medium text-ink">Reference evapotranspiration (ET0): </dt>
                    <dd className="inline num">{w.period.days_with_data > 0 ? `${w.totals.et0_mm} mm over the period` : "Unavailable for the selected period"} (FAO-56 Penman–Monteith), at {w.inputs.location[1]}, {w.inputs.location[0]}</dd></div>
                <div><dt className="inline font-medium text-ink">Plant factor: </dt>
                  <dd className="inline"><span className="num">{w.inputs.plant_factor}</span> for {PLANTING_LABEL[w.inputs.plant_category].toLowerCase()}. {w.inputs.plant_factor_note}</dd></div>
                <div><dt className="inline font-medium text-ink">Irrigated area: </dt>
                  <dd className="inline">{formatArea(w.inputs.irrigated_area_m2)} ({w.inputs.irrigated_area_source})</dd></div>
                <div><dt className="inline font-medium text-ink">Rainfall: </dt><dd className="inline">{w.inputs.rainfall} ({w.period.days_with_data > 0 ? `${w.totals.precip_mm} mm in the period` : "unavailable for the selected period"})</dd></div>
                <div><dt className="inline font-medium text-ink">Source: </dt><dd className="inline" data-testid="water-source">{w.source}</dd></div>
              </dl>
              {canEdit && <FactorForm key={`${w.inputs.plant_category}-${w.inputs.plant_factor}`} w={w} onSaved={load} />}
            </details>
            <div>
              <div className="mb-2 flex items-center justify-between gap-2">
                <h3 className="text-sm font-semibold text-ink">Irrigation schedules <span className="font-normal text-muted">· user-entered</span></h3>
                {canEdit && !form && <Button size="sm" variant="secondary" onClick={() => setForm("new")}><Icon name="plus" className="h-4 w-4" />Add schedule</Button>}
              </div>
              {form && <ScheduleForm siteId={siteId} editing={form === "new" ? null : form} onDone={() => { setForm(null); load(); }} />}
              {schedules.length === 0 && !form && <p className="text-sm text-muted">None.</p>}
              <ul className="divide-y divide-line text-sm">
                {schedules.map((s) => (
                  <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                    <span className="text-ink-2">
                      <span className="num font-medium text-ink">{litres(s.litres_per_day)}</span> on {s.weekdays.map((d) => DAYS[d - 1]).join(", ")} ·{" "}
                      {formatDate(s.start_date)} – {s.end_date ? formatDate(s.end_date) : "ongoing"}{s.notes ? ` · ${s.notes}` : ""}
                    </span>
                    {canEdit && (
                      <span className="flex gap-1">
                        <Button size="sm" variant="ghost" onClick={() => setForm(s)}>Edit</Button>
                        <Button size="sm" variant="ghost" onClick={() => void remove(s)}>Remove</Button>
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          </>
        )}
      </div>
    </Card>
  );
}
