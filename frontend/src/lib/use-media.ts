"use client";

import { useSyncExternalStore } from "react";

/** True while the media query matches (false during server rendering). */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (cb) => {
      const mq = window.matchMedia(query);
      mq.addEventListener("change", cb);
      return () => mq.removeEventListener("change", cb);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

/** Matches Tailwind's lg breakpoint (64rem), where list and map sit side by side. */
export const WIDE = "(min-width: 64rem)";
