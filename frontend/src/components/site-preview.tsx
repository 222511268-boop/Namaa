"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { formatArea, formatDate, formatIndex, PLANTING_LABEL, SITE_TYPE_LABEL, splitSiteName } from "@/lib/format";
import { can } from "@/lib/permissions";
import type { ConditionHistory, Role, SiteDetail } from "@/lib/types";
import { Badge, buttonClass, cx, Icon, Skeleton } from "./ui";

/* Quick look at a green space without leaving the map: condition trend, key figures and the next actions.
   A glass panel floating over the map on wide screens; a bottom sheet on phones. Esc closes it. */

function Sparkline({ history }: { history: ConditionHistory }) {
  const pts = history.observations
    .filter((o) => o.usable && o.ndvi_mean !== null)
    .sort((a, b) => a.acquired_on.localeCompare(b.acquired_on));
  if (pts.length < 2) return <p className="text-cap text-muted">Not enough satellite history to draw a trend yet.</p>;
  const t = pts.map((o) => Date.parse(o.acquired_on));
  const v = pts.map((o) => o.ndvi_mean as number);
  const [t0, t1] = [t[0], t[t.length - 1]];
  const lo = Math.min(...v), hi = Math.max(...v);
  const pad = (hi - lo || 0.1) * 0.15;
  const W = 280, H = 72;
  const x = (ti: number) => ((ti - t0) / (t1 - t0 || 1)) * W;
  const y = (vi: number) => H - ((vi - (lo - pad)) / (hi - lo + 2 * pad || 1)) * H;
  const d = pts.map((_, i) => `${i ? "L" : "M"}${x(t[i]).toFixed(1)},${y(v[i]).toFixed(1)}`).join("");
  const last = pts.length - 1;
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="h-18 w-full overflow-visible" role="img"
        aria-label={`NDVI from ${formatDate(pts[0].acquired_on)} to ${formatDate(pts[last].acquired_on)}: lowest ${formatIndex(lo)}, highest ${formatIndex(hi)}, latest ${formatIndex(v[last])}.`}>
        <path d={`${d}L${W},${H}L0,${H}Z`} fill="var(--c-series-ndvi)" opacity={0.08} />
        <path d={d} fill="none" stroke="var(--c-series-ndvi)" strokeWidth={1.75} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
        <circle cx={x(t[last])} cy={y(v[last])} r={3} fill="var(--c-series-ndvi)" stroke="var(--c-surface)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
      </svg>
      <figcaption className="num mt-1 flex justify-between gap-2 text-cap text-muted">
        <span>{formatDate(pts[0].acquired_on)}</span>
        <span>{formatDate(pts[last].acquired_on)}</span>
      </figcaption>
    </figure>
  );
}

export function SitePreview({ id, role, onClose, className }: { id: string; role: Role; onClose: () => void; className?: string }) {
  const [site, setSite] = useState<SiteDetail | null>(null);
  const [history, setHistory] = useState<ConditionHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadedId, setLoadedId] = useState<string | null>(null);

  useEffect(() => {
    let stale = false;
    Promise.all([api<SiteDetail>(`/api/sites/${id}`), api<ConditionHistory>(`/api/sites/${id}/observations`)])
      .then(([s, h]) => {
        if (stale) return;
        setSite(s);
        setHistory(h);
        setError(null);
      })
      .catch((e) => !stale && setError(errorMessage(e)))
      .finally(() => !stale && setLoadedId(id));
    return () => {
      stale = true;
    };
  }, [id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const ready = loadedId === id && site && history;
  const name = site ? splitSiteName(site.name) : null;
  return (
    <aside aria-label="Green-space preview" data-testid="site-preview"
      className={cx("glass z-20 flex animate-fade-up flex-col rounded-lg p-4", className)}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          {ready && name ? (
            <>
              <h2 className="truncate text-lg font-semibold tracking-tight text-ink" data-testid="preview-name">{name.title}</h2>
              <p className="truncate text-cap text-muted">
                {SITE_TYPE_LABEL[site.site_type]} · <bdi>{site.district_name ?? "No district"}</bdi> · <span className="num">{formatArea(site.area_m2)}</span>
                {name.ref && <> · <span className="num">{name.ref}</span></>}
              </p>
            </>
          ) : (
            <Skeleton className="h-6 w-40" />
          )}
        </div>
        <button type="button" onClick={onClose} className="-mr-1 -mt-1 grid h-9 w-9 shrink-0 place-items-center rounded-md text-muted hover:bg-surface-2 hover:text-ink">
          <span className="sr-only">Close preview</span>
          <Icon name="close" className="h-4 w-4" />
        </button>
      </div>
      {error && <p className="mt-3 text-sm text-danger-ink">{error}</p>}
      {ready ? (
        <div className="mt-3 space-y-3">
          <div className="flex items-end gap-6">
            <div>
              <p className="text-cap text-muted">Latest NDVI</p>
              <p className="num text-2xl font-medium text-ink">{formatIndex(site.latest?.ndvi_mean)}</p>
            </div>
            <div>
              <p className="text-cap text-muted">Usable images</p>
              <p className="num text-2xl font-medium text-ink">{history.usable_count}</p>
            </div>
            <div className="ml-auto flex flex-wrap justify-end gap-1">
              {site.needs_review && <Badge tone="info">Needs review</Badge>}
              {site.low_confidence && <Badge tone="warn">Low confidence</Badge>}
            </div>
          </div>
          <Sparkline history={history} />
          <p className="text-cap text-muted">{PLANTING_LABEL[site.planting_category]}</p>
          <div className="flex flex-wrap gap-2 pt-1">
            <Link href={`/sites/${site.id}`} className={buttonClass("primary", "sm")}>
              Open profile <Icon name="arrow" className="h-4 w-4" />
            </Link>
            {can.manageTasks(role) && (
              <Link href={`/tasks/new?site=${site.id}`} className={buttonClass("secondary", "sm")}>
                <Icon name="clipboard" className="h-4 w-4" /> Create task
              </Link>
            )}
          </div>
        </div>
      ) : (
        !error && <div className="mt-3 space-y-2"><Skeleton className="h-8 w-32" /><Skeleton className="h-18" /></div>
      )}
    </aside>
  );
}
