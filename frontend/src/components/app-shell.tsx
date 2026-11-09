"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, ViewTransition, type ReactNode } from "react";
import { api } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/format";
import { isActive as runActive, onRunFinished, runProgress, useRuns } from "@/lib/live-runs";
import { can, NAV, type NavKey } from "@/lib/permissions";
import { setThemeChoice, useThemeChoice, type ThemeChoice } from "@/lib/theme";
import type { ProcessingRun, Role } from "@/lib/types";
import { useMediaQuery, WIDE } from "@/lib/use-media";
import { PaletteProvider, usePalette } from "./command-palette";
import { useUser } from "./session";
import { ToastProvider, useToast } from "./toast";
import { cx, EmptyState, Icon, Logo, Segmented, type IconName } from "./ui";

const NAV_ICON: Record<NavKey, IconName> = {
  home: "home",
  queue: "inbox",
  tasks: "clipboard",
  map: "map",
  import: "import",
  processing: "satellite",
  users: "users",
  reports: "chart",
  activity: "history",
};

const RUN_DONE: Record<ProcessingRun["kind"], (r: ProcessingRun) => string> = {
  sentinel2: (r) => `Satellite update finished: ${r.items_written} new observations.`,
  landsat_lst: (r) => `Surface temperature update finished: ${r.items_written} site values.`,
  weather: () => "Weather update finished.",
  osm_import: () => "Import finished.",
};

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return (
    pathname === href ||
    pathname.startsWith(`${href}/`) ||
    (href === "/map" && pathname.startsWith("/sites")) ||
    (href === "/queue" && pathname.startsWith("/signals"))
  );
}

function ThemeToggle() {
  const choice = useThemeChoice();
  return (
    <Segmented<ThemeChoice>
      label="Colour theme"
      value={choice}
      onChange={setThemeChoice}
      options={[
        { value: "system", label: "Auto", icon: "monitor" },
        { value: "light", label: "Light", icon: "sun" },
        { value: "dark", label: "Dark", icon: "moon" },
      ]}
    />
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const user = useUser();
  return (
    <ToastProvider>
      <PaletteProvider user={user}>
        <Shell>{children}</Shell>
      </PaletteProvider>
    </ToastProvider>
  );
}

/** Opens the command palette; shows the shortcut on wide screens. */
function SearchButton({ compact = false }: { compact?: boolean }) {
  const { open } = usePalette();
  if (compact)
    return (
      <button onClick={open} className="grid h-touch w-touch place-items-center rounded-md text-ink hover:bg-surface-2">
        <span className="sr-only">Search and actions</span>
        <Icon name="search" />
      </button>
    );
  return (
    <button onClick={open} data-testid="open-palette"
      className="flex h-10 w-full items-center gap-2.5 rounded-md bg-surface-2 px-3 text-sm text-muted ring-1 ring-inset ring-line transition-shadow duration-fast hover:text-ink hover:shadow-glow">
      <Icon name="search" className="h-4 w-4" />
      <span className="flex-1 truncate text-left">Search…</span>
      <kbd className="num rounded-sm bg-surface px-1.5 text-cap text-muted ring-1 ring-line">Ctrl K</kbd>
    </button>
  );
}

/** Live satellite-run status for operators: visible on every page, updates without reloads. */
function LiveRuns({ compact = false }: { compact?: boolean }) {
  const user = useUser();
  const toast = useToast();
  const enabled = can.runProcessing(user.role);
  const runs = useRuns(enabled);
  useEffect(
    () =>
      onRunFinished((r) =>
        toast(r.status === "succeeded"
          ? { tone: "success", text: RUN_DONE[r.kind](r), href: "/processing", action: "View" }
          : { tone: "danger", text: "A processing run failed.", href: "/processing", action: "Details" }),
      ),
    [toast],
  );
  const run = runs?.find(runActive);
  if (!run) return null;
  const progress = runProgress(run);
  const label = run.status === "queued" ? "Satellite update queued" : "Updating satellite data";
  if (compact)
    return (
      <Link href="/processing" className="grid h-touch w-touch place-items-center rounded-md" data-testid="live-run">
        <span className="sr-only">{label}</span>
        <span className="h-2.5 w-2.5 animate-live rounded-full bg-primary shadow-glow" aria-hidden="true" />
      </Link>
    );
  return (
    <Link href="/processing" data-testid="live-run"
      className="mx-3 mb-3 block rounded-md bg-primary-soft px-3 py-2.5 text-cap text-primary-ink ring-1 ring-inset ring-primary/20 transition-shadow duration-fast hover:shadow-glow">
      <span className="flex items-center gap-2 font-medium">
        <span className="h-2 w-2 animate-live rounded-full bg-primary" aria-hidden="true" />
        {label}
      </span>
      {progress !== null && (
        <>
          <span className="mt-2 block h-1 overflow-hidden rounded-full bg-surface" aria-hidden="true">
            <span className="block h-full origin-left rounded-full bg-primary transition-transform duration-slow" style={{ transform: `scaleX(${progress})` }} />
          </span>
          <span className="num mt-1 block">{run.scenes_processed} / {run.scenes_found} scenes</span>
        </>
      )}
    </Link>
  );
}

function Shell({ children }: { children: ReactNode }) {
  const user = useUser();
  const pathname = usePathname();
  const wide = useMediaQuery(WIDE);
  const [open, setOpen] = useState(false);
  const [armed, setArmed] = useState(false); // drawer contents mount on first open
  const menuButton = useRef<HTMLButtonElement>(null);
  const drawer = useRef<HTMLDivElement>(null);
  const items = NAV.filter((n) => n.allowed(user.role));

  // Drawer: Esc closes and returns focus to the menu button; opening moves focus to the first destination.
  useEffect(() => {
    if (!open) return;
    drawer.current?.querySelector<HTMLElement>("nav a")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        menuButton.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  function openMenu() {
    setArmed(true);
    // Two frames: the drawer is painted off-screen first, so the slide-in transition runs on first open too.
    requestAnimationFrame(() => requestAnimationFrame(() => setOpen(true)));
  }

  async function signOut() {
    await api("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    // Full reload on purpose: discards all client state belonging to the signed-out user.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/login");
  }

  const nav = (
    <nav aria-label="Main" className="flex-1 space-y-0.5 px-3">
      {items.map((item) => {
        const active = isActive(pathname, item.href);
        return (
          <Link
            key={item.key}
            href={item.href}
            onClick={() => setOpen(false)}
            aria-current={active ? "page" : undefined}
            data-nav={item.key}
            className={cx(
              "relative flex min-h-10 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors duration-fast",
              active ? "bg-primary-soft text-primary-ink" : "text-ink-2 hover:bg-surface-2 hover:text-ink",
            )}
          >
            {active && <span aria-hidden="true" className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-primary" />}
            <Icon name={NAV_ICON[item.key]} className="h-4.5 w-4.5" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );

  const account = (
    <div className="space-y-3 border-t border-line px-4 py-4">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-ink">{user.full_name}</p>
        <p className="truncate text-cap text-muted">{ROLE_LABEL[user.role]}</p>
      </div>
      <ThemeToggle />
      <div className="-mx-2 space-y-0.5">
        <Link href="/account" onClick={() => setOpen(false)}
          className="flex min-h-9 items-center gap-2 rounded-md px-2 text-cap font-medium text-ink-2 hover:bg-surface-2 hover:text-ink">
          <Icon name="key" className="h-4 w-4" /> Account and password
        </Link>
        <button onClick={signOut}
          className="flex min-h-9 w-full items-center gap-2 rounded-md px-2 text-cap font-medium text-ink-2 hover:bg-surface-2 hover:text-ink">
          <Icon name="logout" className="h-4 w-4" /> Sign out
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-full">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2 focus:shadow-md">
        Skip to content
      </a>

      {/* Only the navigation that fits the screen is rendered: sidebar on wide screens, top bar and drawer on phones. */}
      {wide && (
        <div className="w-sidebar shrink-0 border-r border-line bg-surface print:hidden">
          <aside className="sticky top-0 flex h-screen flex-col">
            <div className="flex h-topbar items-center px-5">
              <Link href="/" aria-label="Namaa home"><Logo /></Link>
            </div>
            <div className="px-3 pb-3"><SearchButton /></div>
            <div className="flex flex-1 flex-col overflow-y-auto">{nav}</div>
            <LiveRuns />
            {account}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile top bar (fixed height: no layout shift) */}
        {!wide && (
        <header className="sticky top-0 z-30 flex h-topbar items-center justify-between border-b border-line bg-surface px-3 print:hidden">
          <Link href="/" aria-label="Namaa home" className="px-1"><Logo /></Link>
          <span className="flex-1" />
          <LiveRuns compact />
          <SearchButton compact />
          <button
            ref={menuButton}
            onClick={openMenu}
            aria-expanded={open}
            aria-controls="mobile-nav"
            className="grid h-touch w-touch place-items-center rounded-md text-ink hover:bg-surface-2"
          >
            <span className="sr-only">Menu</span>
            <Icon name="menu" />
          </button>
        </header>
        )}

        {/* Mobile drawer: stays mounted after first use so it can slide; hidden from AT and focus when closed. */}
        {!wide && armed && (
        <div className={cx("fixed inset-0 z-40", !open && "pointer-events-none")} aria-hidden={!open} inert={!open}>
          <div onClick={() => setOpen(false)}
            className={cx("absolute inset-0 bg-overlay transition-opacity duration-base ease-out-quart", open ? "opacity-100" : "opacity-0")} />
          <div
            id="mobile-nav"
            ref={drawer}
            role="dialog"
            aria-modal="true"
            aria-label="Menu"
            className={cx(
              "absolute inset-y-0 left-0 flex w-sidebar flex-col bg-surface shadow-lg transition-transform duration-slow ease-out-quart",
              open ? "translate-x-0" : "-translate-x-full",
            )}
          >
            <div className="flex h-topbar items-center justify-between px-3">
              <span className="px-1"><Logo /></span>
              <button onClick={() => { setOpen(false); menuButton.current?.focus(); }}
                className="grid h-touch w-touch place-items-center rounded-md text-ink-2 hover:bg-surface-2">
                <span className="sr-only">Close menu</span>
                <Icon name="close" />
              </button>
            </div>
            <div className="mt-2 flex flex-1 flex-col overflow-y-auto">{nav}</div>
            {account}
          </div>
        </div>
        )}

        <main id="main" className="min-w-0 flex-1">
          <ViewTransition default="page">{children}</ViewTransition>
        </main>
      </div>
    </div>
  );
}

/** Client-side guard for screens outside the user's role. The server enforces the same rule. */
export function RequireRole({ allowed, children }: { allowed: (r: Role) => boolean; children: ReactNode }) {
  const user = useUser();
  if (allowed(user.role)) return <>{children}</>;
  return (
    <div className="p-8">
      <EmptyState icon="alert" title="You do not have access to this page">
        Your role ({ROLE_LABEL[user.role]}) cannot use this feature. Contact an administrator if you need access.
      </EmptyState>
    </div>
  );
}
