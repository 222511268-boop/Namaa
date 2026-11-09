"use client";

import { useSyncExternalStore, type CSSProperties, type ReactNode } from "react";
import { Badge, Icon, LinkButton } from "./ui";

/* Signature moment 1: "From orbit to action". A first-visit strip that explains the whole product loop in
   three short steps (about 10 seconds of reading) with one action. Dismissal is remembered per user. */

const EVENT = "namaa-intro-change";
const key = (userId: string) => `namaa-intro-dismissed:${userId}`;

function useDismissed(userId: string) {
  return useSyncExternalStore(
    (cb) => {
      window.addEventListener(EVENT, cb);
      window.addEventListener("storage", cb);
      return () => {
        window.removeEventListener(EVENT, cb);
        window.removeEventListener("storage", cb);
      };
    },
    () => {
      try {
        return localStorage.getItem(key(userId)) === "1";
      } catch {
        return false;
      }
    },
    () => true,
  );
}

function dismiss(userId: string) {
  try {
    localStorage.setItem(key(userId), "1");
  } catch {
    /* storage unavailable: hides for this view only */
  }
  window.dispatchEvent(new Event(EVENT));
}

/** Staggered entrance: each step starts one "fast" duration after the previous (zeroed under reduced motion). */
const delay = (n: number): CSSProperties => ({ animationDelay: `calc(var(--dur-fast) * ${n})` });

function Step({ n, title, text, children }: { n: number; title: string; text: string; children: ReactNode }) {
  return (
    <li className="flex animate-fade-up gap-4 @2xl:flex-col @2xl:gap-3" style={delay(n)}>
      <div className="grid h-16 w-24 shrink-0 place-items-center rounded-md bg-surface-2 ring-1 ring-line @2xl:w-full">
        {children}
      </div>
      <div className="min-w-0">
        <p className="text-cap font-medium text-muted"><span className="num">0{n}</span> · {title}</p>
        <p className="mt-0.5 text-sm text-ink-2">{text}</p>
      </div>
    </li>
  );
}

/** A tiny NDVI trace that falls below its seasonal band: drawn with tokens only. */
function TraceGlyph() {
  return (
    <svg viewBox="0 0 96 40" className="h-10 w-24" aria-hidden="true">
      <rect x="2" y="8" width="92" height="12" rx="2" className="fill-primary-soft" />
      <polyline points="4,15 16,13 28,14 40,12 52,14 62,13 72,22 82,29 90,31" fill="none"
        className="stroke-series-ndvi" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="90" cy="31" r="3.5" className="animate-fade-in fill-signal stroke-surface" strokeWidth="2" style={delay(3)} />
    </svg>
  );
}

export function FirstRun({ userId, canImport }: { userId: string; canImport: boolean }) {
  const dismissed = useDismissed(userId);
  if (dismissed) return null;
  return (
    <section aria-labelledby="first-run-eyebrow" data-testid="first-run"
      className="@container relative animate-fade-in rounded-lg bg-surface p-5 shadow-sm ring-1 ring-line sm:p-6">
      <button type="button" onClick={() => dismiss(userId)}
        className="absolute right-2 top-2 grid h-touch w-touch place-items-center rounded-md text-muted hover:bg-surface-2 hover:text-ink">
        <span className="sr-only">Dismiss introduction</span>
        <Icon name="close" className="h-4 w-4" />
      </button>
      <p id="first-run-eyebrow" className="text-cap font-medium text-primary-ink">How Namaa works</p>
      <h2 className="mt-1 pr-10 text-xl font-semibold tracking-tight text-ink">From orbit to action</h2>
      <ol className="mt-5 grid gap-5 @2xl:grid-cols-3">
        <Step n={1} title="Satellite sees" text="Sentinel-2 measures the greenness of every registered space, image by image.">
          <TraceGlyph />
        </Step>
        <Step n={2} title="Namaa flags" text="When a space stays below its own seasonal range, it enters the attention queue.">
          <span className="animate-fade-in" style={delay(4)}><Badge tone="signal"><Icon name="alert" className="h-3.5 w-3.5" /> Below range</Badge></span>
        </Step>
        <Step n={3} title="Your team confirms" text="A manager reviews the evidence, an inspector checks on site, and the outcome is recorded.">
          <span className="grid h-9 w-9 animate-fade-in place-items-center rounded-full bg-primary text-on-primary" style={delay(5)}>
            <Icon name="check" className="h-5 w-5" />
          </span>
        </Step>
      </ol>
      <div className="mt-6 flex flex-wrap items-center gap-2">
        {canImport
          ? <LinkButton href="/import">Import parks <Icon name="arrow" className="h-4 w-4" /></LinkButton>
          : <LinkButton href="/map">Open map <Icon name="arrow" className="h-4 w-4" /></LinkButton>}
        <button type="button" onClick={() => dismiss(userId)}
          className="min-h-touch rounded-md px-3 text-sm font-medium text-muted hover:bg-surface-2 hover:text-ink">
          Got it
        </button>
      </div>
    </section>
  );
}
