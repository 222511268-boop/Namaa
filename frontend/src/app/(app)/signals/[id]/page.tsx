"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { RequireRole } from "@/components/app-shell";
import { SignalBriefCard } from "@/components/ai-brief";
import { ConditionChart } from "@/components/condition-chart";
import { FindingsView } from "@/components/findings-view";
import { PRIORITY_EXPLANATION, PriorityBar } from "@/components/priority-bar";
import { useUser } from "@/components/session";
import { TaskForm } from "@/components/task-form";
import { ThenNow, type Side } from "@/components/then-now";
import { Alert, Badge, Button, Card, EmptyState, Field, Icon, inputClass, LinkButton, Skeleton } from "@/components/ui";
import { PriorityBadge, SignalStatusBadge, TaskStatusBadge } from "@/components/workflow-badges";
import { api, ApiError, errorMessage } from "@/lib/api";
import { formatArea, formatDate, formatDateTime, formatIndex, OUTCOME_LABEL, signed, SITE_TYPE_LABEL } from "@/lib/format";
import { can } from "@/lib/permissions";
import type { Baseline, ConditionHistory, EvidenceImage, SignalDetail, SignalOutcome, SiteType } from "@/lib/types";

const DECISION_LABEL: Record<string, string> = {
  dismiss: "Dismissed",
  confirm: "Confirmed from the evidence",
  send_for_inspection: "Sent for field inspection",
  inspection_cancelled: "Inspection cancelled; signal reopened",
  record_outcome: "Outcome recorded",
  reopened: "Reopened by new observations",
};

export default function SignalPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <RequireRole allowed={can.viewSignals}>
      <SignalView id={id} />
    </RequireRole>
  );
}

function SignalView({ id }: { id: string }) {
  const user = useUser();
  const [signal, setSignal] = useState<SignalDetail | null>(null);
  const [history, setHistory] = useState<ConditionHistory | null>(null);
  const [baselines, setBaselines] = useState<Baseline[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [side, setSide] = useState<Side>(null);
  const [checklist, setChecklist] = useState("");

  const load = useCallback(
    () =>
      api<SignalDetail>(`/api/signals/${id}`)
        .then((s) =>
          Promise.all([
            api<ConditionHistory>(`/api/sites/${s.site_id}/observations`),
            api<Baseline[]>(`/api/sites/${s.site_id}/baselines`),
          ]).then(([h, b]) => {
            setSignal(s);
            setHistory(h);
            setBaselines(b);
          }),
        )
        .catch((e) => {
          if (e instanceof ApiError && (e.status === 404 || e.status === 422)) setNotFound(true);
          else setError(errorMessage(e));
        }),
    [id],
  );
  useEffect(() => {
    void load();
  }, [load]);

  if (notFound)
    return <div className="p-8"><EmptyState icon="search" title="Signal not found" action={<LinkButton href="/queue" variant="secondary">Back to the queue</LinkButton>} /></div>;
  if (error && !signal) return <div className="p-8"><Alert>{error}</Alert></div>;
  if (!signal || !history)
    return (
      <div className="mx-auto max-w-content space-y-4 px-4 py-6 sm:px-6" aria-busy="true" aria-label="Loading signal">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-9 w-72 max-w-full" />
        <Skeleton className="h-40" />
      </div>
    );

  const obs = signal.evidence.observations ?? [];
  const month = obs.length ? new Date(`${obs[obs.length - 1].date}T00:00:00Z`).toLocaleDateString("en-GB", { month: "long", timeZone: "UTC" }) : "";
  const baseline = baselines.find((b) => obs.length && b.month === new Date(`${obs[obs.length - 1].date}T00:00:00Z`).getUTCMonth() + 1);
  const canDecide = can.decide(user.role);

  const runLength = signal.priority_factors.run_length;
  const thenNow = signal.before_image?.url && signal.after_image?.url;

  return (
    <div className="mx-auto max-w-content px-4 py-6 sm:px-6">
      <Link href="/queue" className="mb-4 inline-flex min-h-9 items-center gap-1 text-sm font-medium text-primary-ink hover:underline">
        <Icon name="back" className="h-4 w-4" /> Attention queue
      </Link>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-cap font-medium text-signal-ink">Signal · vegetation decline</p>
          <h1 className="mt-0.5 text-2xl font-semibold tracking-tight text-ink sm:text-3xl" data-testid="signal-site">{signal.site_name}</h1>
          {signal.site_name_ar && signal.site_name_ar !== signal.site_name && <p className="text-lg text-ink-2" lang="ar" dir="rtl">{signal.site_name_ar}</p>}
          <p className="mt-1 text-sm text-muted">
            {SITE_TYPE_LABEL[signal.site_type as SiteType]} · <bdi>{signal.district_name ?? "No district"}</bdi> · {formatArea(signal.area_m2)} ·{" "}
            <Link href={`/sites/${signal.site_id}`} className="font-medium text-primary-ink underline underline-offset-4">Open site profile</Link>
          </p>
        </div>
        <div className="flex gap-1" data-testid="signal-status"><SignalStatusBadge status={signal.status} outcome={signal.outcome} /></div>
      </div>

      {/* Hero comparison: the one fact the decision rests on. */}
      {signal.boundary_changed && <div className="mb-4"><Alert tone="warn">The site boundary changed after this signal was detected. Its evidence and images refer to the earlier boundary. The condition history reflects the current boundary; refresh historical satellite processing before comparing them.</Alert></div>}
      <section aria-label="Key evidence" data-testid="signal-hero"
        className="grid gap-5 rounded-lg bg-surface p-5 shadow-xs ring-1 ring-line sm:grid-cols-3 sm:p-6">
        <div className="sm:col-span-2">
          <p className="text-sm text-muted">NDVI in the latest {obs.length} usable images, against the usual value for {month}</p>
          <p className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="num text-display font-medium text-signal-ink">{formatIndex(signal.latest_ndvi)}</span>
            <span className="text-xl text-muted" aria-hidden="true">→</span>
            <span className="text-lg text-ink-2">expected <span className="num font-medium text-ink">{formatIndex(signal.baseline_median)}</span></span>
          </p>
          <p className="mt-2 text-sm text-ink-2">
            <span className="num">{signed(signal.deviation)}</span> · <span className="num">{signal.z_score.toFixed(1)}</span> robust SD ·{" "}
            {obs.length ? formatDate(obs[0].date) : "—"} – {formatDate(signal.last_obs_on)}
            {baseline ? ` · baseline from ${baseline.n_obs} observations (${baseline.years})` : ""}
            {runLength && runLength > obs.length ? ` · below range in every usable image since ${formatDate(signal.first_obs_on)} (${runLength} images)` : ""}
          </p>
        </div>
        <div className="sm:border-l sm:border-line sm:pl-5">
          <p className="text-sm text-muted">Priority</p>
          <p className="mt-1"><span className="num text-3xl font-medium text-ink">{Math.round(signal.priority_score)}</span><span className="num text-muted"> / 100</span></p>
          <div className="mt-3"><PriorityBar factors={signal.priority_factors} /></div>
        </div>
        <p className="flex items-start gap-2 text-cap text-muted sm:col-span-3">
          <Icon name="info" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          Greenness is not the same as health: check the images and, if needed, the site itself.
        </p>
      </section>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="min-w-0 space-y-6 lg:col-span-2">
          <Card title="Evidence: NDVI against the seasonal range" action={<Badge tone="info">Satellite-derived</Badge>}>
            <div className="px-4 py-4 sm:px-5">
              <ConditionChart observations={history.observations} baselines={baselines} highlight={obs.map((o) => o.date)}
                compare={thenNow ? { then: signal.before_image!.date, now: signal.after_image!.date, side } : undefined} />
            </div>
          </Card>

          <Card title={thenNow ? "Then / Now (Sentinel-2 true colour)" : "Before and after (Sentinel-2 true colour)"}
            action={thenNow ? <span className="hidden text-cap text-muted sm:inline">Drag the divider or use ← →</span> : undefined}>
            <div className="p-4 sm:p-5" data-testid="evidence-images">
              {thenNow ? (
                <div className="mx-auto max-w-md"><ThenNow then={signal.before_image!} now={signal.after_image!} onSide={setSide} /></div>
              ) : (
                <div className="grid gap-4 sm:grid-cols-2">
                  <Chip label="Before · same season, earlier year" image={signal.before_image} />
                  <Chip label="After · latest image that raised the signal" image={signal.after_image} />
                </div>
              )}
            </div>
            <p className="border-t border-line px-5 py-2.5 text-cap text-muted">
              Yellow outline: site boundary. 10 m resolution, enlarged. {signal.attribution}.
            </p>
          </Card>

          <Card title="Observations that raised the signal">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm" data-testid="trigger-table">
                <thead className="text-cap text-muted">
                  <tr className="border-b border-line">
                    <th scope="col" className="px-5 py-2 font-medium">Image date</th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">NDVI</th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">Expected</th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">Difference</th>
                    <th scope="col" className="px-5 py-2 text-right font-medium">Robust SD</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line text-ink">
                  {obs.map((o) => (
                    <tr key={o.observation_id}>
                      <td className="whitespace-nowrap px-5 py-2" title={o.scene_id}>{formatDate(o.date)}</td>
                      <td className="num px-3 py-2 text-right">{o.ndvi.toFixed(3)}</td>
                      <td className="num px-3 py-2 text-right">{o.baseline_median.toFixed(3)}</td>
                      <td className="num px-3 py-2 text-right text-signal-ink">{signed(o.deviation, 3)}</td>
                      <td className="num px-5 py-2 text-right">{o.z.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {signal.evidence.rule && (
              <p className="border-t border-line px-5 py-2.5 text-cap text-muted">
                Rule: the {signal.evidence.rule.window} latest usable observations are all ≤ {signal.evidence.rule.z_threshold} robust SD and at
                least {signal.evidence.rule.min_drop} NDVI below the seasonal median.
              </p>
            )}
          </Card>
          <SignalBriefCard key={`${id}-${signal.last_obs_on}-${signal.status}`} signalId={id} canGenerate={canDecide} onChecklist={setChecklist} />
        </div>

        <div className="min-w-0 space-y-6">
          <DecisionPanel signal={signal} canDecide={canDecide} onChange={load} checklist={checklist} />
          <Card title="Why this priority">
            <div className="space-y-3 px-5 pb-5 pt-3">
              <PriorityBar factors={signal.priority_factors} showLegend />
              <p className="text-cap text-muted">{PRIORITY_EXPLANATION}</p>
            </div>
          </Card>
          <Card title="Decision history">
            {signal.decisions.length === 0 ? (
              <p className="px-5 pb-5 pt-3 text-sm text-muted">No decisions yet. Detected {formatDateTime(signal.detected_at)}.</p>
            ) : (
              <ol className="mt-2 divide-y divide-line text-sm" data-testid="decision-history">
                {signal.decisions.map((d, i) => (
                  <li key={i} className="px-5 py-3">
                    <p className="font-medium text-ink">{DECISION_LABEL[d.decision] ?? d.decision}{d.outcome ? `: ${OUTCOME_LABEL[d.outcome]}` : ""}</p>
                    {d.reason && <p className="mt-0.5 whitespace-pre-line text-ink-2">{d.reason}</p>}
                    <p className="mt-0.5 text-cap text-muted">{d.user_name ?? "Namaa (automatic)"} · {formatDateTime(d.created_at)}</p>
                  </li>
                ))}
              </ol>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

function Chip({ label, image }: { label: string; image: EvidenceImage | null }) {
  return (
    <figure>
      <div className="aspect-square overflow-hidden rounded-md bg-surface-2 ring-1 ring-line">
        {image?.url ? (
          // eslint-disable-next-line @next/next/no-img-element -- authenticated API image
          <img src={image.url} alt={`${label}, ${formatDate(image.date)}`} className="h-full w-full object-cover" />
        ) : (
          <div className="grid h-full place-items-center p-4 text-center text-sm text-muted">Image unavailable</div>
        )}
      </div>
      <figcaption className="mt-1.5 text-cap text-ink-2">
        <span className="font-medium text-ink">{label}</span>
        <br />
        {image ? `${formatDate(image.date)} · NDVI ${formatIndex(image.ndvi)}` : "No comparable earlier image"}
      </figcaption>
    </figure>
  );
}

function DecisionPanel({ signal, canDecide, onChange, checklist }: { signal: SignalDetail; canDecide: boolean; onChange: () => Promise<void>; checklist: string }) {
  const [mode, setMode] = useState<"none" | "inspect" | "dismiss" | "confirm">("none");
  const [reason, setReason] = useState("");
  const [outcome, setOutcome] = useState<SignalOutcome | "">("");
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const activeTask = signal.tasks.find((t) => t.task_type === "inspection" && t.status !== "cancelled");
  const completed = signal.tasks.find((t) => t.task_type === "inspection" && t.status === "completed");

  async function post(path: string, json: unknown) {
    setBusy(true);
    setError(null);
    setFieldError(null);
    try {
      await api(`/api/signals/${signal.id}/${path}`, { method: "POST", json });
      setMode("none");
      setReason("");
      await onChange();
    } catch (e) {
      if (e instanceof ApiError && Object.keys(e.fieldErrors).length) setFieldError(Object.values(e.fieldErrors)[0]);
      else setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title={signal.status === "open" ? "Decide" : "Status"}>
      <div className="space-y-4 px-5 pb-5 pt-3 text-sm" data-testid="decision-panel">
        {error && <Alert>{error}</Alert>}
        {signal.status === "open" && !canDecide && <p className="text-muted">A green-space manager reviews this signal.</p>}

        {signal.status === "open" && canDecide && mode === "none" && (
          <div className="grid gap-2">
            <Button onClick={() => setMode("inspect")}><Icon name="clipboard" className="h-4 w-4" />Send for inspection</Button>
            <Button variant="secondary" onClick={() => setMode("confirm")}>Confirm from the evidence</Button>
            <Button variant="danger" onClick={() => setMode("dismiss")}>Dismiss…</Button>
          </div>
        )}

        {mode === "inspect" && (
          <TaskForm
            submitLabel="Create inspection task"
            suggestedInstructions={checklist}
            initial={{ title: `Inspect vegetation decline at ${signal.site_name}`.slice(0, 160), priority: signal.priority_score >= 60 ? "high" : "medium", instructions: checklist }}
            onCancel={() => setMode("none")}
            onSubmit={async (v) => {
              await api(`/api/signals/${signal.id}/inspection`, { method: "POST", json: v });
              setMode("none");
              await onChange();
            }}
          />
        )}

        {(mode === "dismiss" || mode === "confirm") && (
          <form onSubmit={(e) => { e.preventDefault(); post(mode, { reason }); }} noValidate className="space-y-3">
            <Field label={mode === "dismiss" ? "Reason for dismissing (required)" : "Note (optional)"} htmlFor="decision-reason"
              error={fieldError ?? undefined} hint={mode === "dismiss" ? "For example: replanting works under way, known irrigation shutdown." : undefined}>
              <textarea id="decision-reason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={2000}
                className={inputClass(!!fieldError)} aria-invalid={!!fieldError || undefined} />
            </Field>
            <div className="flex flex-wrap gap-2">
              <Button type="submit" variant={mode === "dismiss" ? "danger" : "primary"} busy={busy}>
                {mode === "dismiss" ? "Dismiss signal" : "Confirm signal"}
              </Button>
              <Button type="button" variant="secondary" onClick={() => setMode("none")}>Cancel</Button>
            </div>
          </form>
        )}

        {signal.tasks.length > 0 && (
          <div className="divide-y divide-line border-t border-line">
            {signal.tasks.map((t) => (
              <div key={t.id} className="py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Link href={`/tasks/${t.id}`} className="font-medium text-primary-ink underline underline-offset-4">{t.title}</Link>
                  <TaskStatusBadge status={t.status} overdue={t.overdue} />
                </div>
                <p className="mt-1 flex flex-wrap items-center gap-1 text-cap text-muted">{t.assignee_name} · due {formatDate(t.due_date)} · <PriorityBadge priority={t.priority} /></p>
                {t.finding && t.status === "completed" && <div className="mt-2"><FindingsView finding={t.finding} /></div>}
              </div>
            ))}
          </div>
        )}

        {signal.status === "under_inspection" && !completed && activeTask && (
          <p className="text-muted">Waiting for {activeTask.assignee_name} to complete the inspection. The outcome can be recorded afterwards.</p>
        )}

        {signal.status === "under_inspection" && completed && canDecide && (
          <form onSubmit={(e) => { e.preventDefault(); if (outcome) post("outcome", { outcome, note: reason || null }); else setFieldError("Choose an outcome."); }}
            noValidate className="space-y-3" data-testid="outcome-form">
            <fieldset>
              <legend className="mb-1.5 font-medium text-ink">Did the inspection confirm the decline?</legend>
              {(["confirmed", "not_confirmed", "inconclusive"] as SignalOutcome[]).map((o) => (
                <label key={o} className="flex min-h-9 items-center gap-2 text-ink">
                  <input type="radio" name="outcome" value={o} checked={outcome === o} onChange={() => setOutcome(o)} className="h-4 w-4 accent-primary" /> {OUTCOME_LABEL[o]}
                </label>
              ))}
            </fieldset>
            {fieldError && <p role="alert" className="text-cap font-medium text-danger-ink">{fieldError}</p>}
            <Field label="Note (optional)" htmlFor="outcome-note">
              <textarea id="outcome-note" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} className={inputClass()} />
            </Field>
            <Button type="submit" busy={busy}>Record outcome and close</Button>
          </form>
        )}

        {signal.status === "closed" && (
          <p className="text-ink">
            Closed {formatDateTime(signal.closed_at)} with outcome <strong>{signal.outcome ? OUTCOME_LABEL[signal.outcome] : "—"}</strong>
            {signal.outcome_method === "field_inspection" ? " after field inspection." : " from the evidence (desk review)."}
          </p>
        )}
        {signal.status === "dismissed" && (
          <p className="text-ink">Dismissed. It reopens automatically only if three newer observations meet the rule again.</p>
        )}
      </div>
    </Card>
  );
}
