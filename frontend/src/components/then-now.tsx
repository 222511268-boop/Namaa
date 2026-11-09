"use client";

import { useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { formatDate, formatIndex } from "@/lib/format";
import type { EvidenceImage } from "@/lib/types";
import { cx } from "./ui";

/* Signature interaction: "Then / Now". The before and after Sentinel-2 chips become one image with a draggable
   divider (pointer or keyboard: ← → Home End). The image in focus is reported to the chart, which emphasises
   that date, so the imagery and the numbers read as one story. */

export type Side = "then" | "now" | null;

const STEP = 5;

export function ThenNow({ then, now, onSide }: { then: EvidenceImage; now: EvidenceImage; onSide?: (side: Side) => void }) {
  const frame = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState(50); // % of the frame showing the "then" image, from the left
  const [dragging, setDragging] = useState(false);

  function update(next: number) {
    const v = Math.min(100, Math.max(0, next));
    setPos(v);
    onSide?.(v > 55 ? "then" : v < 45 ? "now" : null);
  }

  function fromPointer(e: PointerEvent) {
    const r = frame.current!.getBoundingClientRect();
    update(((e.clientX - r.left) / r.width) * 100);
  }

  function onKey(e: KeyboardEvent) {
    const map: Record<string, number> = { ArrowLeft: pos - STEP, ArrowRight: pos + STEP, Home: 0, End: 100 };
    if (e.key in map) {
      e.preventDefault();
      update(map[e.key]);
    }
  }

  return (
    <figure data-testid="then-now">
      <div
        ref={frame}
        className={cx("relative aspect-square touch-pan-y select-none overflow-hidden rounded-md bg-surface-2 ring-1 ring-line", dragging ? "cursor-grabbing" : "cursor-ew-resize")}
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId);
          setDragging(true);
          fromPointer(e);
        }}
        onPointerMove={(e) => dragging && fromPointer(e)}
        onPointerUp={() => setDragging(false)}
        onPointerCancel={() => setDragging(false)}
      >
        {/* eslint-disable-next-line @next/next/no-img-element -- authenticated API image */}
        <img src={now.url!} alt={`Now: Sentinel-2 true colour, ${formatDate(now.date)}`} draggable={false}
          className="absolute inset-0 h-full w-full object-cover" />
        <div className="absolute inset-0" style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}>
          {/* eslint-disable-next-line @next/next/no-img-element -- authenticated API image */}
          <img src={then.url!} alt={`Then: Sentinel-2 true colour, ${formatDate(then.date)}`} draggable={false}
            className="h-full w-full object-cover" />
        </div>

        <span className="pointer-events-none absolute left-2 top-2 rounded-sm bg-surface/90 px-1.5 py-0.5 text-cap font-medium text-ink">Then</span>
        <span className="pointer-events-none absolute right-2 top-2 rounded-sm bg-surface/90 px-1.5 py-0.5 text-cap font-medium text-ink">Now</span>

        {/* Divider and handle: positioned with transform only. */}
        <div className="pointer-events-none absolute inset-y-0 left-0 w-full" style={{ transform: `translateX(${pos}%)` }}>
          <div className="absolute inset-y-0 -left-px w-0.5 bg-surface shadow-md" />
          <div
            role="slider"
            tabIndex={0}
            aria-label="Then / Now comparison: share of the earlier image shown"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(pos)}
            aria-valuetext={`${Math.round(pos)}% then (${formatDate(then.date)}), ${100 - Math.round(pos)}% now (${formatDate(now.date)})`}
            onKeyDown={onKey}
            onFocus={() => onSide?.(pos > 55 ? "then" : pos < 45 ? "now" : null)}
            onBlur={() => !dragging && onSide?.(null)}
            className="pointer-events-auto absolute top-1/2 grid h-touch w-touch -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-surface text-ink shadow-md ring-1 ring-line"
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="m9 7-5 5 5 5m6-10 5 5-5 5" />
            </svg>
          </div>
        </div>
      </div>
      <figcaption className="mt-2 grid grid-cols-2 gap-3 text-cap">
        <span className="text-ink-2">
          <span className="font-medium text-ink">Then</span> · same season, earlier year<br />
          <span className="num">{formatDate(then.date)} · NDVI {formatIndex(then.ndvi)}</span>
        </span>
        <span className="text-right text-ink-2">
          <span className="font-medium text-ink">Now</span> · image that raised the signal<br />
          <span className="num">{formatDate(now.date)} · NDVI {formatIndex(now.ndvi)}</span>
        </span>
      </figcaption>
    </figure>
  );
}
