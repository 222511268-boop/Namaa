"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { RequireRole } from "@/components/app-shell";
import { PRIORITY_EXPLANATION, PriorityBar } from "@/components/priority-bar";
import { Alert, Badge, Card, cx, EmptyState, Icon, inputClass, PageHeader, Skeleton } from "@/components/ui";
import { SignalStatusBadge } from "@/components/workflow-badges";
import { api, errorMessage } from "@/lib/api";
import { formatArea, formatDate, formatIndex, signed, SITE_TYPE_LABEL } from "@/lib/format";
import { can } from "@/lib/permissions";
import type { District, SignalSummary, SiteType } from "@/lib/types";

const STATUSES = [
  ["active", "Needs attention (open and under inspection)"],
  ["open", "Open"],
  ["under_inspection", "Under inspection"],
  ["dismissed", "Dismissed"],
  ["closed", "Closed"],
  ["all", "All signals"],
] as const;

export default function QueuePage() {
  const [status, setStatus] = useState("active");
  const [districtId, setDistrictId] = useState("");
  const [districts, setDistricts] = useState<District[]>([]);
  const [signals, setSignals] = useState<SignalSummary[] | null>(null);
  const [loadedKey, setLoadedKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const key = useMemo(() => {
    const p = new URLSearchParams({ status });
    if (districtId) p.set("district_id", districtId);
    return p.toString();
  }, [status, districtId]);

  useEffect(() => {
    api<District[]>("/api/districts").then(setDistricts).catch(() => undefined);
  }, []);

  useEffect(() => {
    let stale = false;
    api<SignalSummary[]>(`/api/signals?${key}`)
      .then((s) => !stale && (setSignals(s), setError(null)))
      .catch((e) => !stale && setError(errorMessage(e)))
      .finally(() => !stale && setLoadedKey(key));
    return () => {
      stale = true;
    };
  }, [key]);

  return (
    <RequireRole allowed={can.viewSignals}>
      <div className="mx-auto max-w-content px-4 py-6 sm:px-6 sm:py-8">
        <PageHeader title="Attention queue"
          subtitle="Green spaces whose latest satellite observations are clearly below their usual range for the season." />
        <div className="mb-4 grid grid-cols-2 items-end gap-3 sm:flex sm:flex-wrap">
          <div>
            <label htmlFor="status" className="mb-1 block text-cap font-medium text-muted">Status</label>
            <select id="status" value={status} onChange={(e) => setStatus(e.target.value)} className={inputClass()}>
              {STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="district" className="mb-1 block text-cap font-medium text-muted">District</label>
            <select id="district" value={districtId} onChange={(e) => setDistrictId(e.target.value)} className={inputClass()}>
              <option value="">All districts</option>
              {districts.filter((d) => d.site_count > 0).map((d) => <option key={d.id} value={d.id}>{d.name_en ?? d.name_ar}</option>)}
            </select>
          </div>
          <p className="num col-span-2 text-sm text-muted sm:ml-auto" aria-live="polite" data-testid="queue-count">
            {signals ? `${signals.length} ${signals.length === 1 ? "signal" : "signals"}` : ""}
          </p>
        </div>
        <details className="mb-5 rounded-md bg-surface-2 px-4 py-3 text-sm text-ink-2">
          <summary className="cursor-pointer font-medium text-ink">How signals are raised and ranked</summary>
          <p className="mt-2">A signal is raised when a site&apos;s <strong>three latest usable</strong> Sentinel-2 observations are all at
            least 2 robust standard deviations <em>and</em> 0.05 NDVI below the site&apos;s own median for the same season in
            earlier years. Sites smaller than the monitoring size, or without a previous year of data, are not evaluated.</p>
          <p className="mt-2">{PRIORITY_EXPLANATION}</p>
          <p className="mt-2 font-medium text-ink">Signals are prompts for review, not diagnoses. Decide only after looking at the evidence.</p>
        </details>
        {error && <Alert>{error}</Alert>}
        {!signals && !error && <div className="space-y-3" aria-hidden="true">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-32" />)}</div>}
        {signals && signals.length === 0 && (
          <Card>
            <EmptyState icon="inbox" title={status === "active" ? "Nothing needs attention right now" : "No signals match these filters"}>
              {status === "active"
                ? "No green space currently shows a sustained decline against its seasonal baseline."
                : "Try another status or district."}
            </EmptyState>
          </Card>
        )}
        {signals && signals.length > 0 && (
          <ol className={cx("space-y-3 transition-opacity duration-base", loadedKey !== key && "opacity-60")} data-testid="signal-list">
            {signals.map((s, i) => (
              <li key={s.id}>
                <Link href={`/signals/${s.id}`} className="group block rounded-lg bg-surface p-4 shadow-xs ring-1 ring-line transition-shadow duration-base hover:shadow-md sm:p-5">
                  <div className="flex gap-4">
                    <div className="w-14 shrink-0 text-center">
                      <p className="num text-cap text-muted">#{i + 1}</p>
                      <p className="num text-2xl font-medium text-ink" title="Priority score (0–100)">{Math.round(s.priority_score)}</p>
                      <p className="text-cap text-muted">priority</p>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate font-medium text-ink">{s.site_name}</p>
                          {s.site_name_ar && s.site_name_ar !== s.site_name && (
                            <p className="truncate text-sm text-ink-2" lang="ar" dir="rtl">{s.site_name_ar}</p>
                          )}
                          <p className="text-cap text-muted">
                            {SITE_TYPE_LABEL[s.site_type as SiteType]} · <bdi>{s.district_name ?? "No district"}</bdi> · {formatArea(s.area_m2)}
                          </p>
                        </div>
                        <div className="flex flex-wrap gap-1">
                          <SignalStatusBadge status={s.status} outcome={s.outcome} />
                          {s.reopened_count > 0 && <Badge tone="warn">Reopened ×{s.reopened_count}</Badge>}
                        </div>
                      </div>
                      <p className="mt-2 text-sm text-ink-2">
                        NDVI <strong className="num font-medium text-signal-ink">{formatIndex(s.latest_ndvi)}</strong> → expected{" "}
                        <span className="num text-ink">{formatIndex(s.baseline_median)}</span>{" "}
                        <span className="num">({signed(s.deviation)})</span>
                        <span className="text-muted"> · below range since {formatDate(s.first_obs_on)} (latest {formatDate(s.last_obs_on)})</span>
                      </p>
                      <div className="mt-2"><PriorityBar factors={s.priority_factors} /></div>
                    </div>
                    <Icon name="forward" className="mt-6 hidden h-4 w-4 text-muted transition-transform duration-fast group-hover:translate-x-0.5 sm:block" />
                  </div>
                </Link>
              </li>
            ))}
          </ol>
        )}
      </div>
    </RequireRole>
  );
}
