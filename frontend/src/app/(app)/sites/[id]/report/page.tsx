"use client";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { formatArea, formatDate, formatIndex } from "@/lib/format";
import type { SiteDetail, SiteHeat, WaterEstimate, SignalSummary, Task } from "@/lib/types";
import { FindingsView } from "@/components/findings-view";
import { Alert, Button, Card, LinkButton, PageHeader, Skeleton } from "@/components/ui";

interface SiteReport {
  site: SiteDetail; condition: string; generated_at: string; generated_by_role: string; attribution: string[];
  recent_observations: { acquired_on: string; ndvi: number | null; ndmi: number | null; valid_share: number }[];
  water: WaterEstimate; heat: SiteHeat; signals?: SignalSummary[]; tasks?: Task[];
}
export default function SiteReportPage() {
  const { id } = useParams<{ id: string }>();
  const [report, setReport] = useState<SiteReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { let stale = false; api<SiteReport>(`/api/sites/${id}/report`).then(r => { if (!stale) setReport(r); }).catch(e => { if (!stale) setError(errorMessage(e)); }); return () => { stale = true; }; }, [id]);
  return <div className="mx-auto max-w-content space-y-5 px-4 py-6 sm:px-6">
    <PageHeader title="Green-space report" eyebrow="Namaa · Riyadh pilot" actions={<span className="flex gap-2 print:hidden"><LinkButton href={`/sites/${id}`} variant="secondary">Site profile</LinkButton><Button disabled={!report} onClick={() => window.print()}>Print / save PDF</Button></span>} />
    {error && <Alert>{error}</Alert>}{!report && !error && <Skeleton className="h-60" />}
    {report && <>
      <Card title={report.site.name}><dl className="grid gap-2 p-5 text-sm sm:grid-cols-2">
        <div><dt className="text-muted">District</dt><dd>{report.site.district_name ?? "Unassigned"}</dd></div>
        <div><dt className="text-muted">Condition</dt><dd>{report.condition.replaceAll("_", " ")}</dd></div>
        <div><dt className="text-muted">Area / irrigated area</dt><dd>{formatArea(report.site.area_m2)} / {formatArea(report.water.inputs.irrigated_area_m2)} ({report.water.inputs.irrigated_area_source})</dd></div>
        <div><dt className="text-muted">Type / planting</dt><dd>{report.site.site_type} / {report.site.planting_category}</dd></div>
        <div><dt className="text-muted">Boundary source</dt><dd>{report.site.source} {report.site.source_ref}</dd></div>
        <div><dt className="text-muted">Generated</dt><dd>{new Date(report.generated_at).toLocaleString()} · {report.generated_by_role}</dd></div>
      </dl></Card>
      <Card title="Recent usable satellite observations"><div className="overflow-x-auto p-5"><table className="w-full text-left text-sm"><thead><tr>{["Acquisition", "NDVI", "NDMI", "Valid pixels"].map(h => <th key={h} className="pb-2">{h}</th>)}</tr></thead><tbody>{report.recent_observations.map(o => <tr key={o.acquired_on} className="border-t border-line"><td className="py-2">{formatDate(o.acquired_on)}</td><td>{formatIndex(o.ndvi)}</td><td>{formatIndex(o.ndmi)}</td><td>{Math.round(o.valid_share * 100)}%</td></tr>)}</tbody></table>{!report.recent_observations.length && <p>No usable observations available.</p>}</div></Card>
      <Card title="Water demand · Estimate"><div className="space-y-2 p-5 text-sm">
        <p>{report.water.period.start} – {report.water.period.end}: {report.water.period.days_with_data > 0 ? `${report.water.totals.demand_m3} m³ estimated demand` : "Estimated demand unavailable"}, {report.water.period.days_with_data}/{report.water.period.days} days with data.</p>
        <p>{report.water.formula}. ET0: {report.water.period.days_with_data > 0 ? `${report.water.totals.et0_mm} mm` : "unavailable"}; plant factor: {report.water.inputs.plant_factor}; irrigated area: {report.water.inputs.irrigated_area_m2} m².</p>
        <p>{report.water.inputs.plant_factor_note} {report.water.inputs.rainfall}</p>
        {report.water.comparison?.days_compared ? <p>Schedule comparison over {report.water.comparison.days_compared} days: {report.water.comparison.scheduled_m3} m³ scheduled; {report.water.comparison.demand_m3} m³ estimated; difference {report.water.comparison.difference_m3} m³ ({report.water.comparison.difference_pct ?? "unavailable"}%). User-entered schedule, not measured consumption.</p> : <p>{report.water.has_schedule ? "No days in this period have both stored ET0 and a schedule." : "No schedule entered; comparison unavailable."}</p>}
        {report.water.notice && <p>{report.water.notice}</p>}<p className="text-cap text-muted">{report.water.source}</p>
      </div></Card>
      <Card title="Land surface temperature · Satellite-derived"><div className="space-y-2 p-5 text-sm">
        {report.heat.latest ? <p>{formatDate(report.heat.latest.acquired_on)}: site {report.heat.latest.site_c ?? "unavailable"} °C; surroundings {report.heat.latest.surround_c ?? "unavailable"} °C; difference {report.heat.latest.difference_c ?? "unavailable"} °C. {report.heat.latest.platform} · {report.heat.latest.scene_id}.</p> : <p>No usable surface temperature observation available.</p>}
        <p>{report.heat.resolution} {report.heat.method}</p>
      </div></Card>
      {report.signals && <Card title="Signals and decisions"><ul className="divide-y divide-line p-5 text-sm">{report.signals.map(s => <li key={s.id} className="py-2">Detected {formatDate(s.detected_at)} · {s.status.replaceAll("_", " ")} · {s.outcome?.replaceAll("_", " ") ?? "No outcome"} · priority {s.priority_score}/100 · heat contribution {s.priority_factors.heat ?? "unavailable"}</li>)}</ul>{!report.signals.length && <p className="p-5">No signals recorded.</p>}</Card>}
      {report.tasks && <Card title="Tasks and field findings"><div className="divide-y divide-line p-5">{report.tasks.map(t => <section key={t.id} className="space-y-2 py-3"><h3 className="font-medium">{t.title}</h3><p className="text-sm">{t.status.replaceAll("_", " ")} · due {formatDate(t.due_date)}{t.overdue ? " · overdue" : ""} · {t.assignee_name}</p>{t.finding && <FindingsView finding={t.finding} />}</section>)}{!report.tasks.length && <p>No tasks in your permission scope.</p>}</div></Card>}
      <footer className="space-y-1 text-cap text-muted"><p>Data attribution</p>{report.attribution.map(a => <p key={a}>{a}</p>)}</footer>
    </>}
  </div>;
}
