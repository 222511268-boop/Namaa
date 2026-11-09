"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { FirstRun } from "@/components/first-run";
import { OperationalOverview } from "@/components/operational-overview";
import { useUser } from "@/components/session";
import { useToast } from "@/components/toast";
import { Alert, Button, Card, EmptyState, Icon, LinkButton, PageHeader, Skeleton, Stat } from "@/components/ui";
import { RunStatusBadge } from "@/components/run-status";
import { api, errorMessage } from "@/lib/api";
import { isActive, runProgress, smartRange, startRun, useRuns } from "@/lib/live-runs";
import { formatArea, formatDate, formatDateTime, ROLE_LABEL } from "@/lib/format";
import { can } from "@/lib/permissions";
import type { WorkspaceSummary } from "@/lib/types";

/** The one figure each role should act on first (Stripe-style hero metric). */
function Hero({ summary, role }: { summary: WorkspaceSummary; role: WorkspaceSummary["role"] }) {
  let label: string, value: number, detail: string, href: string, cta: string;
  if (summary.signals) {
    label = "Signals to review";
    value = summary.signals.open;
    detail = `${summary.signals.under_inspection} under inspection`;
    href = "/queue";
    cta = "Open the attention queue";
  } else if (summary.tasks) {
    label = role === "inspector" ? "My open tasks" : "Open tasks";
    value = summary.tasks.open;
    detail = summary.tasks.overdue ? `${summary.tasks.overdue} overdue` : "Nothing overdue";
    href = "/tasks";
    cta = role === "inspector" ? "Go to my tasks" : "Open tasks";
  } else {
    label = "Active green spaces";
    value = summary.sites.active;
    detail = `${formatArea(summary.sites.total_area_m2)} in total`;
    href = "/map";
    cta = "Open map";
  }
  const urgent = summary.tasks && !summary.signals && summary.tasks.overdue > 0;
  return (
    <Link href={href} data-testid="workflow-stats"
      className="group flex h-full flex-col justify-between gap-6 rounded-lg bg-surface p-6 shadow-xs ring-1 ring-line transition-shadow duration-base hover:shadow-md">
      <div>
        <p className="text-sm font-medium text-muted">{label}</p>
        <p className="num mt-1 text-display font-medium text-ink">{value}</p>
        <p className={urgent ? "mt-1 text-sm font-medium text-danger-ink" : "mt-1 text-sm text-muted"}>{detail}</p>
      </div>
      <span className="inline-flex items-center gap-2 text-sm font-medium text-primary-ink">
        {cta}
        <Icon name="arrow" className="h-4 w-4 transition-transform duration-fast group-hover:translate-x-0.5" />
      </span>
    </Link>
  );
}

export default function OverviewPage() {
  const user = useUser();
  const [summary, setSummary] = useState<WorkspaceSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<WorkspaceSummary>("/api/summary").then(setSummary).catch((e) => setError(errorMessage(e)));
  }, []);

  const firstName = user.full_name.split(" ")[0];
  return (
    <div className="mx-auto max-w-content px-4 py-6 sm:px-6 sm:py-8">
      <PageHeader eyebrow={`${ROLE_LABEL[user.role]} · Riyadh pilot`} title={`Welcome, ${firstName}`}
        actions={can.editSites(user.role) ? (
          <LinkButton href="/sites/new" variant="secondary" size="sm"><Icon name="plus" className="h-4 w-4" />Green space</LinkButton>
        ) : undefined} />
      {error && <Alert>{error}</Alert>}
      {!summary && !error && (
        <div className="space-y-6" aria-busy="true" aria-label="Loading overview">
          <Skeleton className="h-40" />
          <Skeleton className="h-24" />
        </div>
      )}
      {summary && (
        <div className="space-y-8" data-testid={`home-${user.role}`}>
          <FirstRun userId={user.id} canImport={can.editSites(user.role)} />
          {can.viewOverview(user.role) && <OperationalOverview />}
          <div className="grid gap-6 lg:grid-cols-3">
            <div className={"latest_run" in summary ? "lg:col-span-2" : "lg:col-span-3"}>
              {summary.sites.active === 0 ? (
                <Card className="h-full">
                  <EmptyState title="No green spaces registered yet"
                    action={can.editSites(user.role) ? <LinkButton href="/import">Import from OpenStreetMap</LinkButton> : undefined}>
                    {can.editSites(user.role)
                      ? "Start by importing parks for a district, or draw a boundary yourself."
                      : "Green spaces added by a manager will appear here and on the map."}
                  </EmptyState>
                </Card>
              ) : (
                <Hero summary={summary} role={user.role} />
              )}
            </div>
            {"latest_run" in summary && <SatelliteCard summary={summary} />}
          </div>

          <section aria-label="Workspace figures">
            <div className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-3 lg:grid-cols-6">
              {summary.tasks && summary.signals && (
                <>
                  <Stat label={user.role === "inspector" ? "My open tasks" : "Open tasks"} value={summary.tasks.open} href="/tasks" />
                  <Stat label="Overdue tasks" value={summary.tasks.overdue} />
                </>
              )}
              <Stat label="Green spaces" value={summary.sites.active} hint={formatArea(summary.sites.total_area_m2)} href="/map" />
              <Stat label="With satellite history" value={summary.sites.with_observations}
                hint={summary.latest_observation_on ? `Latest ${formatDate(summary.latest_observation_on)}` : "None yet"} />
              <Stat label="Need review" value={summary.sites.needs_review} />
              <Stat label="Low confidence" value={summary.sites.low_confidence} />
            </div>
          </section>

          {can.editSites(user.role) && summary.sites.needs_review > 0 && (
            <Link href="/map" className="group flex items-center justify-between gap-4 rounded-lg px-1 py-2 text-sm text-ink-2 hover:text-ink">
              <span>
                <span className="font-medium text-ink">{summary.sites.needs_review} imported sites</span> still need a confirmed name and planting
                category.
              </span>
              <Icon name="forward" className="h-4 w-4 shrink-0 text-muted transition-transform duration-fast group-hover:translate-x-0.5" />
            </Link>
          )}
        </div>
      )}
    </div>
  );
}

/** Latest satellite processing with live progress and a one-click update from the newest stored image. */
function SatelliteCard({ summary }: { summary: WorkspaceSummary }) {
  const toast = useToast();
  const runs = useRuns(true);
  const [busy, setBusy] = useState(false);
  const run = runs?.find((r) => r.kind === "sentinel2") ?? summary.latest_run ?? null;
  const active = run ? isActive(run) : false;
  const progress = run ? runProgress(run) : null;
  const range = smartRange(summary.latest_observation_on);

  async function update() {
    setBusy(true);
    try {
      await startRun(range);
      toast({ tone: "info", text: `Run queued for ${range.start} to ${range.end}.`, href: "/processing", action: "Follow" });
    } catch (e) {
      toast({ tone: "danger", text: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="satellite-card">
    <Card title="Latest satellite processing" className="h-full">
      <div className="space-y-3 px-5 pb-5 pt-3 text-sm">
        {run ? (
          <>
            <RunStatusBadge status={run.status} />
            {active && progress !== null && (
              <div className="h-1 overflow-hidden rounded-full bg-surface-2" aria-hidden="true">
                <div className="h-full origin-left rounded-full bg-primary transition-transform duration-slow" style={{ transform: `scaleX(${progress})` }} />
              </div>
            )}
            <p className="text-ink-2">
              <span className="num text-ink">{run.items_written}</span> observations from <span className="num text-ink">{run.scenes_found}</span> scenes
              <span className="block text-cap text-muted">{formatDateTime(run.created_at)}{run.requested_by_name ? ` · ${run.requested_by_name}` : ""}</span>
            </p>
          </>
        ) : (
          <p className="text-muted">No satellite runs yet.</p>
        )}
        <Button variant="secondary" size="sm" busy={busy} disabled={active} onClick={update}>
          <Icon name="refresh" className="h-4 w-4" /> {active ? "Update running" : "Update now"}
        </Button>
        <p className="text-cap text-muted">New images from <span className="num">{range.start}</span> to yesterday, all active sites.</p>
      </div>
    </Card>
    </div>
  );
}
