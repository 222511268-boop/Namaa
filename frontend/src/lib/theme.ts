"use client";

import { useSyncExternalStore } from "react";

/* Theme preference (System / Light / Dark). The choice lives in localStorage and is applied as
   data-theme on <html>; layout.tsx applies it again before first paint. */

export type ThemeChoice = "system" | "light" | "dark";
const KEY = "namaa-theme";
const EVENT = "namaa-theme-change";

function readChoice(): ThemeChoice {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

export function setThemeChoice(choice: ThemeChoice) {
  try {
    if (choice === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, choice);
  } catch {
    /* storage unavailable: the choice still applies for this page view */
  }
  if (choice === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = choice;
  window.dispatchEvent(new Event(EVENT));
}

function subscribe(onChange: () => void) {
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  window.addEventListener(EVENT, onChange);
  window.addEventListener("storage", onChange);
  mq.addEventListener("change", onChange);
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("storage", onChange);
    mq.removeEventListener("change", onChange);
  };
}

export function useThemeChoice(): ThemeChoice {
  return useSyncExternalStore(subscribe, readChoice, () => "system");
}

function resolved(): "light" | "dark" {
  const c = readChoice();
  if (c !== "system") return c;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** The theme actually showing: changes when the user picks one or the OS setting changes. */
export function useResolvedTheme(): "light" | "dark" {
  return useSyncExternalStore(subscribe, resolved, () => "light");
}

/** Reads a design token (e.g. "--c-primary") for canvas/WebGL drawing, which cannot use CSS classes. */
export function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
