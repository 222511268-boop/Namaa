"use client";

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, errorMessage } from "@/lib/api";
import { formatIndex, SITE_TYPE_LABEL, splitSiteName } from "@/lib/format";
import { smartRange, startRun } from "@/lib/live-runs";
import { can, NAV, type NavKey } from "@/lib/permissions";
import { setThemeChoice, useResolvedTheme } from "@/lib/theme";
import type { SiteSummary, User, WorkspaceSummary } from "@/lib/types";
import { useToast } from "./toast";
import { cx, Icon, type IconName } from "./ui";

/* Command palette (Ctrl/Cmd+K) and global keyboard shortcuts: jump to any green space, page or action
   without moving through menus. Everything offered respects the user's role (the server enforces it too). */

type Command = { id: string; group: "Green spaces" | "Recent" | "Go to" | "Actions"; label: string; hint?: string; icon: IconName; keys?: string; run: () => void | Promise<void> };

const PaletteContext = createContext<{ open: () => void; showShortcuts: () => void }>({ open: () => undefined, showShortcuts: () => undefined });
export const usePalette = () => useContext(PaletteContext);

const NAV_ICON: Record<NavKey, IconName> = { home: "home", queue: "inbox", tasks: "clipboard", map: "map", import: "import", processing: "satellite", users: "users", reports: "chart", activity: "history" };
const RECENT_KEY = "namaa-recent-sites";

type Recent = { id: string; name: string };
/** Remember a visited green space for the palette's "Recent" group (this device only). */
export function rememberSite(site: Recent) {
  try {
    const list: Recent[] = JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]");
    localStorage.setItem(RECENT_KEY, JSON.stringify([site, ...list.filter((s) => s.id !== site.id)].slice(0, 5)));
  } catch {
    /* storage unavailable */
  }
}
function recentSites(): Recent[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]");
  } catch {
    return [];
  }
}

const typing = (t: EventTarget | null) =>
  t instanceof HTMLElement && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName));

const SHORTCUTS: [string, string][] = [
  ["Ctrl K  /  ⌘ K", "Search green spaces, pages and actions"],
  ["/", "Search the current list (opens the palette elsewhere)"],
  ["N", "Register a new green space (managers)"],
  ["Esc", "Close a panel, dialog or inline editor"],
  ["?", "Show these shortcuts"],
];

export function PaletteProvider({ user, children }: { user: User; children: ReactNode }) {
  const router = useRouter();
  const toast = useToast();
  const theme = useResolvedTheme();
  const [open, setOpen] = useState(false);
  const [help, setHelp] = useState(false);
  const [q, setQ] = useState("");
  const [sites, setSites] = useState<SiteSummary[]>([]);
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);

  const show = useCallback(() => {
    returnFocus.current = document.activeElement as HTMLElement | null;
    setQ("");
    setActive(0);
    setOpen(true);
  }, []);
  const close = useCallback(() => {
    setOpen(false);
    returnFocus.current?.focus?.();
  }, []);

  // Global shortcuts.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (open) close();
        else show();
        return;
      }
      if (open || help || e.ctrlKey || e.metaKey || e.altKey || typing(e.target)) return;
      if (e.key === "/") {
        const search = document.querySelector<HTMLInputElement>("[data-shortcut-search]:not([hidden])");
        e.preventDefault();
        if (search && search.offsetParent !== null) search.focus();
        else show();
      } else if (e.key === "?") {
        e.preventDefault();
        setHelp(true);
      } else if (e.key.toLowerCase() === "n" && can.editSites(user.role)) {
        e.preventDefault();
        router.push("/sites/new");
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, help, show, close, router, user.role]);

  // Live green-space search.
  useEffect(() => {
    if (!open || !q.trim()) return;
    let stale = false;
    const t = setTimeout(() => {
      api<SiteSummary[]>(`/api/sites?q=${encodeURIComponent(q.trim())}`)
        .then((list) => !stale && setSites(list.slice(0, 6)))
        .catch(() => undefined);
    }, 120);
    return () => {
      stale = true;
      clearTimeout(t);
    };
  }, [q, open]);

  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);

  const go = useCallback((href: string) => () => router.push(href), [router]);

  const commands = useMemo<Command[]>(() => {
    const needle = q.trim().toLowerCase();
    const match = (s: string) => !needle || needle.split(/\s+/).every((w) => s.toLowerCase().includes(w));
    const out: Command[] = [];
    if (needle) {
      for (const s of sites) {
        const { title, ref } = splitSiteName(s.name);
        out.push({
          id: `site-${s.id}`, group: "Green spaces", icon: "leaf", label: title,
          hint: [ref, SITE_TYPE_LABEL[s.site_type], s.district_name, s.latest ? `NDVI ${formatIndex(s.latest.ndvi_mean)}` : null].filter(Boolean).join(" · "),
          run: go(`/sites/${s.id}`),
        });
      }
    } else {
      for (const s of recentSites()) out.push({ id: `recent-${s.id}`, group: "Recent", icon: "clock", label: s.name, run: go(`/sites/${s.id}`) });
    }
    const actions: (Command | false)[] = [
      can.editSites(user.role) && { id: "new-site", group: "Actions", icon: "plus", label: "Register a green space", keys: "N", run: go("/sites/new") },
      can.editSites(user.role) && { id: "import", group: "Actions", icon: "import", label: "Import parks from OpenStreetMap", run: go("/import") },
      can.runProcessing(user.role) && {
        id: "update-satellite", group: "Actions", icon: "satellite", label: "Update satellite data", hint: "From the latest image to yesterday, all active sites",
        run: async () => {
          try {
            const summary = await api<WorkspaceSummary>("/api/summary");
            const range = smartRange(summary.latest_observation_on);
            await startRun(range);
            toast({ tone: "info", text: `Run queued. Satellite update ${range.start} to ${range.end} is running in the background.`, href: "/processing", action: "Follow" });
          } catch (e) {
            toast({ tone: "danger", text: errorMessage(e) });
          }
        },
      },
      can.manageTasks(user.role) && { id: "new-task", group: "Actions", icon: "clipboard", label: "Create a task", run: go("/tasks/new") },
      can.manageUsers(user.role) && { id: "new-user", group: "Actions", icon: "users", label: "Create a user account", run: go("/users#new") },
      { id: "theme", group: "Actions", icon: theme === "dark" ? "sun" : "moon", label: theme === "dark" ? "Switch to light theme" : "Switch to dark theme", run: () => setThemeChoice(theme === "dark" ? "light" : "dark") },
      { id: "shortcuts", group: "Actions", icon: "key", label: "Keyboard shortcuts", keys: "?", run: () => setHelp(true) },
    ];
    const pages: Command[] = NAV.filter((n) => n.allowed(user.role)).map((n) => ({
      id: `nav-${n.key}`, group: "Go to", icon: NAV_ICON[n.key], label: n.label, run: go(n.href),
    }));
    return [...out, ...pages.filter((c) => match(c.label)), ...actions.filter((a): a is Command => !!a && match(a.label))];
  }, [q, sites, user.role, go, theme, toast]);

  const activeIndex = Math.min(active, Math.max(0, commands.length - 1));

  function choose(cmd: Command) {
    setOpen(false);
    void cmd.run();
  }

  function onInputKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((activeIndex + 1) % Math.max(1, commands.length));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((activeIndex - 1 + commands.length) % Math.max(1, commands.length));
    } else if (e.key === "Enter" && commands[activeIndex]) {
      e.preventDefault();
      choose(commands[activeIndex]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      close();
    }
  }

  useEffect(() => {
    document.getElementById(`cmd-${commands[activeIndex]?.id}`)?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, commands]);

  const ctx = useMemo(() => ({ open: show, showShortcuts: () => setHelp(true) }), [show]);

  let lastGroup = "";
  return (
    <PaletteContext.Provider value={ctx}>
      {children}
      {open && (
        <div className="fixed inset-0 z-50 flex items-start justify-center px-3 pt-20 sm:pt-32" onMouseDown={(e) => e.target === e.currentTarget && close()}>
          <div className="absolute inset-0 animate-fade-in bg-overlay" aria-hidden="true" />
          <div role="dialog" aria-modal="true" aria-label="Command palette" data-testid="command-palette"
            className="relative w-full max-w-xl animate-fade-up overflow-hidden rounded-lg bg-surface shadow-lg ring-1 ring-line">
            <div className="flex items-center gap-3 border-b border-line px-4">
              <Icon name="search" className="h-4 w-4 shrink-0 text-muted" />
              <input ref={input} value={q} onChange={(e) => { setQ(e.target.value); setActive(0); if (!e.target.value.trim()) setSites([]); }}
                onKeyDown={onInputKey} placeholder="Search green spaces, pages and actions…"
                role="combobox" aria-expanded="true" aria-controls="cmd-list" aria-activedescendant={commands[activeIndex] ? `cmd-${commands[activeIndex].id}` : undefined}
                aria-label="Search green spaces, pages and actions" aria-autocomplete="list"
                className="h-14 min-w-0 flex-1 bg-transparent text-base text-ink placeholder:text-muted focus:outline-none focus-visible:shadow-none focus-visible:outline-none" />
              <kbd className="num hidden rounded-sm bg-surface-2 px-1.5 py-0.5 text-cap text-muted sm:inline">Esc</kbd>
            </div>
            <ul id="cmd-list" role="listbox" aria-label="Results" className="max-h-96 overflow-y-auto p-2">
              {commands.length === 0 && <li className="px-3 py-6 text-center text-sm text-muted">No matches. Try a park name in English or Arabic.</li>}
              {commands.map((cmd, i) => {
                const header = cmd.group !== lastGroup ? cmd.group : null;
                lastGroup = cmd.group;
                return (
                  <li key={cmd.id} role="presentation">
                    {header && <p className="px-3 pb-1 pt-2 text-cap font-medium text-muted" role="presentation">{header}</p>}
                    <div id={`cmd-${cmd.id}`} role="option" aria-selected={i === activeIndex} onMouseMove={() => setActive(i)} onClick={() => choose(cmd)}
                      className={cx("flex min-h-11 cursor-pointer items-center gap-3 rounded-md px-3 py-2 transition-colors duration-fast",
                        i === activeIndex ? "bg-primary-soft text-primary-ink shadow-glow" : "text-ink")}>
                      <Icon name={cmd.icon} className="h-4 w-4 shrink-0 opacity-80" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium">{cmd.label}</span>
                        {cmd.hint && <span className="block truncate text-cap text-muted">{cmd.hint}</span>}
                      </span>
                      {cmd.keys && <kbd className="num rounded-sm bg-surface-2 px-1.5 py-0.5 text-cap text-muted">{cmd.keys}</kbd>}
                      {i === activeIndex && <Icon name="arrow" className="h-4 w-4 shrink-0" />}
                    </div>
                  </li>
                );
              })}
            </ul>
            <p className="flex flex-wrap gap-x-4 gap-y-1 border-t border-line px-4 py-2 text-cap text-muted">
              <span><kbd className="num">↑ ↓</kbd> move</span>
              <span><kbd className="num">Enter</kbd> open</span>
              <span><kbd className="num">?</kbd> all shortcuts</span>
            </p>
          </div>
        </div>
      )}
      {help && <ShortcutsDialog onClose={() => setHelp(false)} />}
    </PaletteContext.Provider>
  );
}

function ShortcutsDialog({ onClose }: { onClose: () => void }) {
  const closeBtn = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeBtn.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 grid place-items-center px-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="absolute inset-0 animate-fade-in bg-overlay" aria-hidden="true" />
      <div role="dialog" aria-modal="true" aria-labelledby="shortcuts-title" className="relative w-full max-w-md animate-fade-up rounded-lg bg-surface p-5 shadow-lg ring-1 ring-line">
        <div className="mb-3 flex items-center justify-between">
          <h2 id="shortcuts-title" className="text-lg font-semibold text-ink">Keyboard shortcuts</h2>
          <button ref={closeBtn} onClick={onClose} className="grid h-9 w-9 place-items-center rounded-md text-muted hover:bg-surface-2 hover:text-ink">
            <span className="sr-only">Close</span>
            <Icon name="close" className="h-4 w-4" />
          </button>
        </div>
        <dl className="grid grid-cols-label gap-x-6 gap-y-2.5 text-sm">
          {SHORTCUTS.map(([k, v]) => (
            <div key={k} className="contents">
              <dt><kbd className="num rounded-sm bg-surface-2 px-1.5 py-0.5 text-cap text-ink">{k}</kbd></dt>
              <dd className="text-ink-2">{v}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
