import { FACTOR_LABEL } from "@/lib/format";
import type { PriorityFactors } from "@/lib/types";

// Categorical slots 1-5 of the validated reference palette (tokens --c-factor-1..5, tuned per theme;
// adjacent pairs pass the CVD checks in light and dark).
const FACTOR_COLOR: Record<string, string> = {
  severity: "var(--c-factor-1)",
  persistence: "var(--c-factor-2)",
  size: "var(--c-factor-3)",
  site_type: "var(--c-factor-4)",
  heat: "var(--c-factor-5)",
};
const ORDER = ["severity", "persistence", "size", "site_type", "heat"] as const;

/** Stacked bar of factor points (0-100) with the values also written out, so colour is never the only cue. */
export function PriorityBar({ factors, showLegend = false }: { factors: PriorityFactors; showLegend?: boolean }) {
  return (
    <div>
      <div className="flex h-2 w-full gap-0.5 overflow-hidden rounded-full bg-surface-2" aria-hidden="true">
        {ORDER.map((k) =>
          (factors[k] ?? 0) > 0 ? (
            <span key={k} className="h-full first:rounded-l-full last:rounded-r-full"
              style={{ width: `${factors[k]}%`, background: FACTOR_COLOR[k] }} />
          ) : null,
        )}
      </div>
      <p className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-cap text-ink-2">
        {ORDER.map((k) =>
          k === "heat" && factors.heat == null ? (
            <span key={k} className="inline-flex items-center gap-1 text-muted" data-testid="no-heat"
              title="No recent surface temperature data: scored on the other four factors.">
              {showLegend && <span className="h-2 w-2 rounded-sm ring-1 ring-line-strong" />}
              No heat data
            </span>
          ) : (
            <span key={k} className="inline-flex items-center gap-1">
              {showLegend && <span className="h-2 w-2 rounded-sm" style={{ background: FACTOR_COLOR[k] }} />}
              {FACTOR_LABEL[k]} <span className="num font-medium text-ink">{(factors[k] as number).toFixed(1)}</span>
            </span>
          ),
        )}
      </p>
    </div>
  );
}

export const PRIORITY_EXPLANATION =
  "Priority (0–100) = severity up to 50 (how far below normal) + persistence up to 20 (how long every usable image " +
  "has been below range, full marks at 30 days) + size up to 20 (larger sites score higher) + site type up to 10 (parks and gardens score highest). " +
  "When recent Landsat surface temperature is available, these four are scaled to 90% and surface heat adds up to 10: " +
  "the surrounding area's temperature as a percentile among monitored sites on the same date. Sites without heat data are scored on the four factors.";
