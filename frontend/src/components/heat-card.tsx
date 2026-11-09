"use client";

import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { SiteHeat } from "@/lib/types";
import { Alert, Badge, Card, Icon, LinkButton, Skeleton } from "./ui";

const c = (v: number | null) => (v === null ? "–" : `${v.toFixed(1)} °C`);

/** Land surface temperature of the site and its surroundings (US19). */
export function HeatCard({ siteId, canProcess }: { siteId: string; canProcess: boolean }) {
  const [h, setH] = useState<SiteHeat | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<SiteHeat>(`/api/sites/${siteId}/heat`).then(setH).catch((e) => setError(errorMessage(e)));
  }, [siteId]);
  return (
    <Card id="heat" title={<span className="inline-flex items-center gap-2"><Icon name="thermo" className="h-4 w-4 text-signal-ink" /> Surface heat</span>}
      action={<Badge tone="info" title="Calculated from Landsat thermal imagery">Satellite-derived</Badge>}>
      <div className="space-y-3 px-5 py-4" data-testid="heat-card">
        {error && <Alert>{error}</Alert>}
        {!h && !error && <Skeleton className="h-20" />}
        {h && !h.latest && (
          <div className="text-sm text-muted">
            <p>No clear Landsat surface temperature for this site yet.</p>
            {canProcess && <LinkButton href="/processing" variant="secondary" size="sm" className="mt-2">Update surface heat</LinkButton>}
          </div>
        )}
        {h?.latest && (
          <>
            <dl className="grid grid-cols-3 gap-3">
              <div><dt className="text-cap text-muted">Site</dt><dd className="num text-xl font-medium text-ink" data-testid="lst-site">{c(h.latest.site_c)}</dd></div>
              <div><dt className="text-cap text-muted">Surroundings ({h.surround_m} m)</dt><dd className="num text-xl font-medium text-ink" data-testid="lst-surround">{c(h.latest.surround_c)}</dd></div>
              <div><dt className="text-cap text-muted">Difference</dt><dd className="num text-xl font-medium text-ink">
                {h.latest.difference_c === null ? "–" : `${h.latest.difference_c > 0 ? "+" : h.latest.difference_c < 0 ? "−" : ""}${Math.abs(h.latest.difference_c).toFixed(1)} °C`}</dd></div>
            </dl>
            <p className="text-cap text-muted">
              Land surface temperature on {formatDate(h.latest.acquired_on)} ({h.latest.platform}). Surface temperature is not air
              temperature; irrigated vegetation is usually cooler than its surroundings.
            </p>
            {h.priority_heat && (
              <p className="text-sm text-ink-2">
                Surroundings have a temperature percentile of <span className="num font-medium text-ink">{h.priority_heat.percentile}</span> among{" "}
                {h.priority_heat.sites_compared} monitored sites on that date; this sets the heat factor in signal priority.
              </p>
            )}
          </>
        )}
        {h && (
          <p className="text-cap text-muted" data-testid="lst-resolution">
            {h.resolution}. {h.method} {h.attribution}.
          </p>
        )}
      </div>
    </Card>
  );
}
