"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { formatDate, formatIndex, percent } from "@/lib/format";
import type { Baseline, Observation } from "@/lib/types";
import { cx } from "./ui";

/*
 * Two small multiples (NDVI, NDMI) sharing one time axis - never a dual-axis chart.
 * Each panel is a single series, so its title names it and no legend box is needed.
 * Interaction: a crosshair snaps to the nearest acquisition date; the tooltip lists both values.
 * Keyboard: focus the chart and use Left/Right/Home/End. A table view lists every value.
 * All colours are design tokens (CSS variables), so the chart follows light and dark themes.
 */

type Series = { key: "ndvi_mean" | "ndmi_mean"; title: string; color: string; description: string };
const SERIES: Series[] = [
  { key: "ndvi_mean", title: "NDVI · vegetation greenness", color: "var(--c-series-ndvi)", description: "Higher means greener, denser vegetation." },
  { key: "ndmi_mean", title: "NDMI · vegetation moisture", color: "var(--c-series-ndmi)", description: "Higher means more water in the leaves." },
];

const PANEL_H = 132;
const PANEL_GAP = 28;
const PAD = { top: 10, right: 16, bottom: 8, left: 44 };
const AXIS_H = 26;
const COMPARE_H = 18; // label strip for the Then / Now markers
const TOOLTIP_W = 208;

function niceDomain(values: number[]): [number, number] {
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  if (hi - lo < 0.1) {
    const mid = (hi + lo) / 2;
    lo = mid - 0.05;
    hi = mid + 0.05;
  }
  const pad = (hi - lo) * 0.15;
  return [Math.floor((lo - pad) * 20) / 20, Math.ceil((hi + pad) * 20) / 20];
}

function ticks([lo, hi]: [number, number]): number[] {
  const step = hi - lo > 0.6 ? 0.2 : hi - lo > 0.3 ? 0.1 : 0.05;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(Math.round(v * 100) / 100);
  return out;
}

function monthTicks(t0: number, t1: number, width: number): Date[] {
  const months = Math.max(1, Math.round((t1 - t0) / (30 * 86400e3)));
  const every = Math.max(1, Math.ceil(months / Math.max(2, Math.floor(width / 90))));
  const d = new Date(t0);
  const out: Date[] = [];
  let cur = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1));
  while (cur.getTime() <= t1) {
    out.push(cur);
    cur = new Date(Date.UTC(cur.getUTCFullYear(), cur.getUTCMonth() + every, 1));
  }
  return out;
}

type Band = { x0: number; x1: number; lo: number; hi: number; median: number };

/** Dates of the "Then / Now" image pair; `side` is the image currently in focus (from the swipe divider). */
type ChartCompare = { then: string; now: string; side: "then" | "now" | null };

/**
 * Optional overlays (Sprint 2): the seasonal baseline band on the NDVI panel (median ± 2 robust SD per month of
 * the target year), highlighted observations (those that raised a signal), and the Then / Now image dates.
 */
export function ConditionChart({
  observations,
  baselines,
  highlight,
  compare,
}: {
  observations: Observation[];
  baselines?: Baseline[];
  highlight?: string[];
  compare?: ChartCompare;
}) {
  const usable = useMemo(
    () => observations.filter((o) => o.usable && o.ndvi_mean !== null).sort((a, b) => a.acquired_on.localeCompare(b.acquired_on)),
    [observations],
  );
  const wrap = useRef<HTMLDivElement>(null);
  // Width is measured from the container before drawing: a fixed first width would overflow small screens.
  const [width, setWidth] = useState<number | null>(null);
  const [active, setActive] = useState<number | null>(null);
  const [showTable, setShowTable] = useState(false);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.floor(e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, [showTable, usable.length]);

  if (usable.length === 0) return null;

  const times = usable.map((o) => Date.parse(`${o.acquired_on}T00:00:00Z`));
  const t0 = times[0];
  const t1 = times.length > 1 ? times[times.length - 1] : t0 + 86400e3;
  const w = width ?? 0;
  const plotW = Math.max(0, w - PAD.left - PAD.right);
  const x = (t: number) => PAD.left + ((t - t0) / (t1 - t0 || 1)) * plotW;
  const xDate = (iso: string) => x(Date.parse(`${iso}T00:00:00Z`));

  const bands: Band[] = (baselines ?? [])
    .filter((b) => b.available && b.median_ndvi !== null && b.robust_sd !== null)
    .map((b) => {
      const start = Date.UTC(b.target_year, b.month - 1, 1);
      const end = Date.UTC(b.target_year, b.month, 1);
      return {
        x0: Math.max(start, t0),
        x1: Math.min(end, t1),
        lo: b.median_ndvi! - 2 * b.robust_sd!,
        hi: b.median_ndvi! + 2 * b.robust_sd!,
        median: b.median_ndvi!,
      };
    })
    .filter((b) => b.x1 > b.x0);
  const bandYears = baselines?.find((b) => b.available)?.years;
  const marked = new Set(highlight ?? []);

  function nearest(px: number) {
    let best = 0;
    for (let i = 1; i < times.length; i++) if (Math.abs(x(times[i]) - px) < Math.abs(x(times[best]) - px)) best = i;
    return best;
  }

  function onPointer(e: PointerEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    setActive(nearest(e.clientX - rect.left));
  }

  function onKey(e: KeyboardEvent) {
    const last = usable.length - 1;
    const map: Record<string, number> = {
      ArrowLeft: Math.max(0, (active ?? last + 1) - 1),
      ArrowRight: Math.min(last, (active ?? -1) + 1),
      Home: 0,
      End: last,
    };
    if (e.key in map) {
      e.preventDefault();
      setActive(map[e.key]);
    } else if (e.key === "Escape") setActive(null);
  }

  const a = active !== null ? usable[active] : null;
  const strip = compare ? COMPARE_H : 0;
  const TOTAL_H = strip + SERIES.length * (PANEL_H + PANEL_GAP) + AXIS_H;
  const labelX = (iso: string) => Math.min(Math.max(xDate(iso), PAD.left + 16), w - PAD.right - 16);
  const inRange = (iso: string) => {
    const t = Date.parse(`${iso}T00:00:00Z`);
    return t >= t0 && t <= t1;
  };

  return (
    <div className="min-w-0">
      <div className="mb-2 flex items-center justify-end">
        <button onClick={() => setShowTable((s) => !s)} aria-expanded={showTable}
          className="min-h-9 rounded-md px-2.5 text-cap font-medium text-primary-ink hover:bg-primary-soft">
          {showTable ? "Show chart" : "Show as table"}
        </button>
      </div>
      {showTable ? (
        <ObservationTable observations={observations} />
      ) : (
        <div ref={wrap} className="relative w-full">
          {/* Reserve the chart's height before the first measurement so nothing below it shifts. */}
          {width === null ? (
            <div style={{ height: (compare ? COMPARE_H : 0) + SERIES.length * (PANEL_H + PANEL_GAP) + AXIS_H }} aria-hidden="true" />
          ) : (
            <svg
              width={w}
              height={TOTAL_H}
              role="img"
              aria-label={`NDVI and NDMI for ${usable.length} usable acquisitions from ${formatDate(usable[0].acquired_on)} to ${formatDate(usable[usable.length - 1].acquired_on)}. Use the arrow keys to read values, or show the table.`}
              tabIndex={0}
              onPointerMove={onPointer}
              onPointerLeave={() => setActive(null)}
              onKeyDown={onKey}
              onBlur={() => setActive(null)}
              className="block touch-pan-y select-none"
              data-testid="condition-chart"
            >
              {SERIES.map((s, si) => {
                const values = usable.map((o) => o[s.key] as number);
                const withBand = s.key === "ndvi_mean" ? bands : [];
                const dom = niceDomain([...values, ...withBand.flatMap((b) => [b.lo, b.hi])]);
                const top = strip + si * (PANEL_H + PANEL_GAP) + 22;
                const y = (v: number) => top + PAD.top + (1 - (v - dom[0]) / (dom[1] - dom[0])) * (PANEL_H - PAD.top - PAD.bottom);
                const path = usable.map((o, i) => `${i ? "L" : "M"}${x(times[i]).toFixed(1)},${y(o[s.key] as number).toFixed(1)}`).join("");
                const showMarkers = usable.length <= 40;
                return (
                  <g key={s.key}>
                    <text x={PAD.left} y={top - 6} className="fill-ink text-cap font-medium">{s.title}</text>
                    {ticks(dom).map((t) => (
                      <g key={t}>
                        <line x1={PAD.left} x2={w - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--c-line)" strokeWidth={1} />
                        <text x={PAD.left - 6} y={y(t)} textAnchor="end" dominantBaseline="middle" className="num fill-muted text-cap">{t.toFixed(2)}</text>
                      </g>
                    ))}
                    {withBand.map((b) => (
                      <g key={b.x0}>
                        <rect x={x(b.x0)} width={Math.max(1, x(b.x1) - x(b.x0))} y={y(b.hi)} height={Math.max(1, y(b.lo) - y(b.hi))}
                          fill={s.color} opacity={0.12} />
                        <line x1={x(b.x0)} x2={x(b.x1)} y1={y(b.median)} y2={y(b.median)} stroke={s.color} strokeOpacity={0.45}
                          strokeDasharray="4 3" />
                      </g>
                    ))}
                    {compare && (["then", "now"] as const).filter((k) => inRange(compare[k])).map((k) => (
                      <line key={k} x1={xDate(compare[k])} x2={xDate(compare[k])} y1={top + PAD.top} y2={top + PANEL_H - PAD.bottom}
                        stroke="var(--c-ink)" strokeWidth={compare.side === k ? 2 : 1}
                        strokeOpacity={compare.side === null || compare.side === k ? 0.7 : 0.25}
                        data-testid={`compare-${k}`} />
                    ))}
                    <path d={path} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
                    {s.key === "ndvi_mean" && usable.map((o, i) =>
                      marked.has(o.acquired_on) ? (
                        <circle key={`m${o.acquired_on}`} cx={x(times[i])} cy={y(o[s.key] as number)} r={7} fill="none"
                          stroke="var(--c-signal)" strokeWidth={2} data-testid="signal-marker" />
                      ) : null,
                    )}
                    {showMarkers && usable.map((o, i) => (
                      <circle key={o.acquired_on} cx={x(times[i])} cy={y(o[s.key] as number)} r={active === i ? 5 : 3.5}
                        fill={s.color} stroke="var(--c-surface)" strokeWidth={2} />
                    ))}
                    {!showMarkers && a && active !== null && (
                      <circle cx={x(times[active])} cy={y(a[s.key] as number)} r={5} fill={s.color} stroke="var(--c-surface)" strokeWidth={2} />
                    )}
                  </g>
                );
              })}
              {/* shared time axis */}
              {monthTicks(t0, t1, plotW).map((d) => (
                <text key={d.toISOString()} x={x(d.getTime())} y={TOTAL_H - 8} textAnchor="middle" className="fill-muted text-cap">
                  {d.toLocaleDateString("en-GB", { month: "short", year: "2-digit", timeZone: "UTC" })}
                </text>
              ))}
              {compare && (["then", "now"] as const).filter((k) => inRange(compare[k])).map((k) => (
                <text key={k} x={labelX(compare[k])} y={12} textAnchor="middle"
                  className={cx("text-cap font-medium", compare.side === k ? "fill-ink" : "fill-muted")}>
                  {k === "then" ? "Then" : "Now"}
                </text>
              ))}
              {active !== null && (
                <line x1={x(times[active])} x2={x(times[active])} y1={14 + strip} y2={TOTAL_H - AXIS_H} stroke="var(--c-ink-2)" strokeWidth={1} strokeDasharray="3 3" />
              )}
            </svg>
          )}
          {(bands.length > 0 || marked.size > 0) && (
            <p className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-cap text-ink-2" data-testid="baseline-legend">
              {bands.length > 0 && (
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-3 w-5 rounded-sm opacity-20" style={{ background: "var(--c-series-ndvi)" }} />
                  Expected range for the season (median ± 2 robust SD{bandYears ? `, from ${bandYears}` : ""})
                </span>
              )}
              {marked.size > 0 && (
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-3 w-3 rounded-full border-2 border-signal" /> Observations that raised the signal
                </span>
              )}
            </p>
          )}
          {a && active !== null && (
            <div
              role="status"
              className="pointer-events-none absolute top-8 z-10 w-52 rounded-md bg-surface px-3 py-2 text-cap shadow-md ring-1 ring-line"
              style={{ left: Math.min(Math.max(0, x(times[active]) + 12), w - TOOLTIP_W - 4) }}
            >
              <p className="mb-1 font-medium text-ink-2">{formatDate(a.acquired_on)}</p>
              {SERIES.map((s) => (
                <p key={s.key} className="flex items-center gap-2">
                  <span className="h-0.5 w-3" style={{ background: s.color }} />
                  <span className="num font-medium text-ink">{formatIndex(a[s.key])}</span>
                  <span className="text-muted">{s.key === "ndvi_mean" ? "NDVI" : "NDMI"}</span>
                </p>
              ))}
              <p className="mt-1 text-muted">Clear pixels: <span className="num">{percent(a.valid_share)}</span> ({a.valid_pixels}/{a.total_pixels})</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ObservationTable({ observations }: { observations: Observation[] }) {
  const rows = [...observations].sort((a, b) => b.acquired_on.localeCompare(a.acquired_on));
  return (
    <div className="max-h-80 overflow-auto rounded-md ring-1 ring-line">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Satellite observations for this site</caption>
        <thead className="sticky top-0 bg-surface-2 text-cap text-muted">
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">Date</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">NDVI</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">NDMI</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">Clear pixels</th>
            <th scope="col" className="px-3 py-2 font-medium">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((o) => (
            <tr key={o.acquired_on} className={cx(o.usable ? "text-ink" : "text-muted")}>
              <td className="whitespace-nowrap px-3 py-1.5" title={o.scene_id}>{formatDate(o.acquired_on)}</td>
              <td className="num px-3 py-1.5 text-right">{formatIndex(o.ndvi_mean)}</td>
              <td className="num px-3 py-1.5 text-right">{formatIndex(o.ndmi_mean)}</td>
              <td className="num px-3 py-1.5 text-right">{percent(o.valid_share)}</td>
              <td className="px-3 py-1.5">{o.usable ? "Usable" : "Not used (cloud or shadow)"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
