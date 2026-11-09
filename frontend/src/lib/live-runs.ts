"use client";

import { useEffect, useSyncExternalStore } from "react";
import { api } from "./api";
import { utcIsoDaysAgo } from "./format";
import type { ProcessingRun } from "./types";

/* Live processing status shared by the shell indicator, the Overview card and the Satellite data page.
   One poll for the whole app: every 4 s while a run is queued or running and someone is watching; idle otherwise. */

let runs: ProcessingRun[] | null = null;
let timer: ReturnType<typeof setTimeout> | undefined;
let inflight: Promise<void> | null = null;
const listeners = new Set<() => void>();
const finishedListeners = new Set<(run: ProcessingRun) => void>();

export const isActive = (r: ProcessingRun) => r.status === "queued" || r.status === "running";

function emit() {
  listeners.forEach((l) => l());
}

function schedule() {
  clearTimeout(timer);
  if (listeners.size && runs?.some(isActive)) timer = setTimeout(() => void refreshRuns(), 4000);
}

/** Fetch the latest runs now (for example right after starting one). */
function refreshRuns(afterCurrent = false): Promise<void> {
  // A read that began before a mutation cannot confirm the new run. Follow it with a fresh request.
  if (afterCurrent && inflight) return inflight.then(() => refreshRuns());
  inflight ??= api<ProcessingRun[]>("/api/processing-runs")
    .then((next) => {
      const before = new Map((runs ?? []).map((r) => [r.id, r.status]));
      runs = next;
      for (const r of next) {
        const was = before.get(r.id);
        if ((was === "queued" || was === "running") && !isActive(r)) finishedListeners.forEach((l) => l(r));
      }
      emit();
    })
    .catch(() => undefined)
    .finally(() => {
      inflight = null;
      schedule();
    });
  return inflight;
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  schedule();
  return () => {
    listeners.delete(cb);
    if (!listeners.size) clearTimeout(timer);
  };
}

/** Runs, newest first, kept live. Pass enabled=false for roles that cannot see processing runs. */
export function useRuns(enabled = true): ProcessingRun[] | null {
  const value = useSyncExternalStore(subscribe, () => runs, () => null);
  useEffect(() => {
    if (enabled) void refreshRuns();
  }, [enabled]);
  return enabled ? value : null;
}

/** Called once when a run that was being watched finishes (succeeded or failed). */
export function onRunFinished(cb: (run: ProcessingRun) => void) {
  finishedListeners.add(cb);
  return () => {
    finishedListeners.delete(cb);
  };
}

export function runProgress(r: ProcessingRun): number | null {
  if (r.kind === "osm_import" || !r.scenes_found) return null;
  return Math.min(1, r.scenes_processed / r.scenes_found);
}

const KEY = "namaa-last-run-range";

/**
 * Smart default range: from the latest stored satellite image to yesterday (repeating a range never duplicates
 * observations), or the last 90 days when nothing has been processed yet.
 */
export function smartRange(latestObservation: string | null | undefined): { start: string; end: string } {
  const end = utcIsoDaysAgo(1);
  const start = latestObservation && latestObservation < end ? latestObservation : utcIsoDaysAgo(90);
  return { start, end };
}

export function lastUsedRange(): { start: string; end: string } | null {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "null");
    return v && typeof v.start === "string" && typeof v.end === "string" ? v : null;
  } catch {
    return null;
  }
}

/** Queue a run (Sentinel-2 by default) and start watching it. */
export async function startRun(
  range: { start: string; end: string },
  siteIds?: string[],
  kind: "sentinel2" | "landsat_lst" | "weather" = "sentinel2",
): Promise<ProcessingRun> {
  const run = await api<ProcessingRun>("/api/processing-runs", {
    method: "POST",
    json: { kind, start_date: range.start, end_date: range.end, ...(siteIds ? { site_ids: siteIds } : {}) },
  });
  try {
    localStorage.setItem(KEY, JSON.stringify(range));
  } catch {
    /* storage unavailable */
  }
  runs = [run, ...(runs ?? []).filter(r => r.id !== run.id)];
  emit();
  schedule();
  await refreshRuns(true);
  return run;
}

/** Queue a new run with the same type and settings as an earlier one (US23). */
export async function rerun(runId: string): Promise<ProcessingRun> {
  const run = await api<ProcessingRun>(`/api/processing-runs/${runId}/rerun`, { method: "POST" });
  runs = [run, ...(runs ?? []).filter(r => r.id !== run.id)];
  emit();
  schedule();
  await refreshRuns(true);
  return run;
}
