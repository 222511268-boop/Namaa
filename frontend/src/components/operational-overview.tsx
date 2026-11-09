"use client";

import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { can } from "@/lib/permissions";
import type { AiBrief, District, Overview, OverviewSummaryContent } from "@/lib/types";
import { useUser } from "./session";
import { AiLabel, Cited, FactList, useAiStatus } from "./ai-brief";
import { Alert, Button, Card, Field, inputClass, Skeleton } from "./ui";

const today = () => new Date().toISOString().slice(0, 10);
const initialStart = () => { const d = new Date(); d.setUTCDate(d.getUTCDate() - 89); return d.toISOString().slice(0, 10); };

/** Filters, counts, exports and narrative all use the same server-side reporting scope. */
export function OperationalOverview() {
  const user = useUser();
  const status = useAiStatus();
  const [districts, setDistricts] = useState<District[]>([]);
  const [district, setDistrict] = useState("");
  const [start, setStart] = useState(initialStart);
  const [end, setEnd] = useState(today);
  const [data, setData] = useState<{ query: string; overview: Overview } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aiError, setAiError] = useState<string | null>(null);
  const [requested, setRequested] = useState(false);
  const [revision, setRevision] = useState(0);
  const [brief, setBrief] = useState<{ query: string; value: AiBrief<OverviewSummaryContent> } | null>(null);
  const [busy, setBusy] = useState(false);
  const valid = Boolean(start && end && end >= start);
  const query = new URLSearchParams({ start, end, ...(district ? { district_id: district } : {}) }).toString();
  useEffect(() => { api<District[]>("/api/districts").then(setDistricts).catch(() => undefined); }, []);
  useEffect(() => {
    if (!valid) return;
    let stale = false;
    api<Overview>(`/api/overview?${query}`).then(overview => {
      if (!stale) { setData({ query, overview }); setError(null); }
    }).catch(e => { if (!stale) setError(errorMessage(e)); });
    return () => { stale = true; };
  }, [query, valid]);
  useEffect(() => {
    if (!requested || !valid) return;
    let stale = false;
    // This effect owns an external request; defer its status update with the request itself.
    void Promise.resolve().then(() => { if (!stale) { setBusy(true); setAiError(null); } });
    api<AiBrief<OverviewSummaryContent>>("/api/overview/summary", {
      method: "POST", json: { start, end, district_id: district ? Number(district) : null, force: revision > 0 },
    }).then(value => { if (!stale) setBrief({ query, value }); })
      .catch(e => { if (!stale) setAiError(errorMessage(e)); })
      .finally(() => { if (!stale) setBusy(false); });
    return () => { stale = true; };
  }, [requested, query, revision, valid, start, end, district]);
  const ov = valid && data?.query === query ? data.overview : null;
  const ai = valid && brief?.query === query ? brief.value : null;
  const facts = new Map((ai?.facts ?? []).map(f => [f.id, f]));
  return (
    <section className="space-y-5" aria-label="Operational overview">
      <div className="flex flex-wrap items-end gap-3 print:hidden">
        <Field label="District" htmlFor="overview-district"><select id="overview-district" className={inputClass()} value={district} onChange={e => setDistrict(e.target.value)}>
          <option value="">All districts</option>{districts.map(d => <option key={d.id} value={d.id}>{d.name_en ?? d.name_ar}</option>)}
        </select></Field>
        <Field label="From" htmlFor="overview-start"><input id="overview-start" type="date" value={start} onInput={e => setStart(e.currentTarget.value)} className={inputClass()} /></Field>
        <Field label="Through" htmlFor="overview-end"><input id="overview-end" type="date" value={end} min={start} onInput={e => setEnd(e.currentTarget.value)} className={inputClass()} /></Field>
        <Button variant="secondary" disabled={!ov} onClick={() => window.print()}>Print overview</Button>
      </div>
      {!valid && <Alert>Choose a valid date range.</Alert>}
      {error && <Alert>{error}</Alert>}
      {!ov && valid && !error && <Skeleton className="h-40" />}
      {ov && <>
        <p className="text-sm text-muted">{ov.filters.district_name ?? "All districts"} · {ov.filters.start} through {ov.filters.end}. Generated {new Date(ov.generated_at).toLocaleString()}.</p>
        <div className="grid gap-4 md:grid-cols-2">
          {[
            { title: `Green spaces (${ov.sites_total})`, values: ov.conditions, labels: ov.condition_labels, note: ov.definitions.conditions },
            { title: `Signals (${ov.signals_total})`, values: ov.signals, note: ov.definitions.signals },
            { title: `Tasks (${ov.tasks_total})`, values: ov.tasks, note: `${ov.definitions.tasks} Overdue: ${ov.overdue_tasks}. ${ov.definitions.overdue}` },
            { title: "Review outcomes", values: { ...ov.outcomes, ...ov.outcomes_by_method }, note: `${ov.definitions.outcomes} Field confirmation rate: ${ov.confirmation_rate_pct === null ? "unavailable" : `${ov.confirmation_rate_pct}%`}.` },
          ].map(section => <Card key={section.title} title={section.title}><div className="space-y-3 p-5">
            <dl className="space-y-2">{Object.entries(section.values).map(([key, value]) => <div key={key} className="flex justify-between gap-3"><dt className="text-sm text-ink-2">{section.labels?.[key as keyof typeof section.labels] ?? key.replaceAll("_", " ")}</dt><dd className="num font-medium">{value}</dd></div>)}</dl>
            <p className="text-cap text-muted">{section.note}</p>
          </div></Card>)}
        </div>
        <div className="space-y-2 print:hidden">
          <h2 className="font-semibold">CSV exports</h2><p className="text-sm text-muted">Site exports reflect the district and current state. Signal and task exports use the period above (detected and created dates).</p>
          <div className="flex flex-wrap gap-4 text-sm text-primary-ink underline">
            <a href={`/api/exports/sites.csv?${district ? `district_id=${district}` : ""}`}>Green spaces CSV</a>
            {can.exportSignals(user.role) && <a href={`/api/exports/signals.csv?${query}`}>Signals CSV</a>}
            {can.exportTasks(user.role) && <a href={`/api/exports/tasks.csv?${query}`}>Tasks CSV</a>}
          </div>
        </div>
        {can.summariseWithAi(user.role) && <Card title="AI overview summary" action={<span className="print:hidden"><Button size="sm" variant="secondary" busy={busy} disabled={status?.enabled === false} onClick={() => { if (requested) setRevision(r => r + 1); else setRequested(true); }}>{ai ? "Regenerate" : "Generate summary"}</Button></span>}>
          <div className="space-y-3 p-5" aria-live="polite" aria-busy={busy}>
            {status?.enabled === false && <p className="text-sm text-muted">AI assistance is not configured on this server.</p>}
            {aiError && <Alert tone="warn">{aiError}</Alert>}
            {!ai && <p className="text-sm text-muted">An advisory narrative of the selected figures. After requesting it, changing filters generates a new summary.</p>}
            {ai && <><AiLabel text={ai.label} /><p className="font-medium">{ai.content.headline}</p>
              {ai.content.paragraphs.map((ev, i) => <p key={i} className="text-sm text-ink-2"><Cited ev={ev} facts={facts} prefix="overview-fact" /></p>)}
              <ul className="list-disc pl-5 text-sm">{ai.content.watch_items.map((ev, i) => <li key={i}><Cited ev={ev} facts={facts} prefix="overview-fact" /></li>)}</ul>
              <FactList facts={ai.facts} prefix="overview-fact" /><p className="text-cap text-muted">{ai.model} · {ai.prompt_version} · {new Date(ai.created_at).toLocaleString()}</p></>}
          </div>
        </Card>}
        <p className="text-cap text-muted">Sources: OpenStreetMap contributors (ODbL); modified Copernicus Sentinel data; USGS Landsat via Microsoft Planetary Computer; Open-Meteo (CC BY 4.0). Water values are estimates.</p>
      </>}
    </section>
  );
}
