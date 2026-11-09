"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from "react";

/* UI primitives. Every colour, size, radius, shadow and duration comes from the design tokens in globals.css. */

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

/* ------------------------------------------------------------------ brand */

/** Mark: a sprout inside a satellite orbit (current colour). */
export function Mark({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <circle cx="16" cy="16" r="14.5" fill="none" stroke="currentColor" strokeWidth="1.25" opacity="0.35" />
      <ellipse cx="16" cy="16" rx="14.5" ry="5.5" fill="none" stroke="currentColor" strokeWidth="1.25" opacity="0.55"
        transform="rotate(-28 16 16)" />
      <circle cx="28.4" cy="9.7" r="1.6" fill="currentColor" />
      <path d="M16 24v-8.5m0 0c-.6-3-3-4.6-6-4.3 1.9.5 4 2 6 4.3Zm0 0c.6-3 3-4.6 6-4.3-1.9.5-4 2-6 4.3Z"
        fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-2.5 text-primary-ink", className)}>
      <Mark />
      <span className="text-lg font-semibold tracking-tight text-ink">
        Namaa <span className="font-normal text-muted" lang="ar">نماء</span>
      </span>
    </span>
  );
}

/* ------------------------------------------------------------------ icons */

const paths = {
  home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z",
  map: "M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2Zm0 0v14m6-12v14",
  import: "M12 3v12m0 0-4-4m4 4 4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2",
  satellite: "M13 7 9 3 5 7l4 4m4-4 4 4m-4-4 2-2m2 6 4 4-4 4-4-4m4-4-6 6m-4-6-2 2m6 4 2 2M3 21l3-3",
  users: "M16 19v-1a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v1M9 10a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm13 9v-1a4 4 0 0 0-3-3.9M16 4.1a3 3 0 0 1 0 5.8",
  plus: "M12 5v14M5 12h14",
  search: "m21 21-4.3-4.3M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15Z",
  logout: "M15 17l5-5-5-5m5 5H9m3 9H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7",
  info: "M12 16v-4m0-4h.01M12 22a10 10 0 1 1 0-20 10 10 0 0 1 0 20Z",
  alert: "M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z",
  check: "M20 6 9 17l-5-5",
  edit: "M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z",
  back: "M15 18l-6-6 6-6",
  forward: "m9 18 6-6-6-6",
  arrow: "M5 12h14m-6-6 6 6-6 6",
  refresh: "M21 12a9 9 0 1 1-3-6.7L21 8m0-5v5h-5",
  leaf: "M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.5 19 2c1 2 2 4.2 2 8 0 5.5-4.8 10-10 10Zm0 0c0-4 2-7 6-9",
  close: "M18 6 6 18M6 6l12 12",
  menu: "M4 6h16M4 12h16M4 18h16",
  inbox: "M22 12h-6l-2 3h-4l-2-3H2m20 0-3.5-7h-13L2 12m20 0v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-6",
  clipboard: "M9 4h6a1 1 0 0 1 1 1v1H8V5a1 1 0 0 1 1-1Zm-1 2H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-2M8 13l2 2 5-5",
  key: "M15 7a4 4 0 1 1-3.4 6.1L4 20.7V17h3v-3h3l1.6-1.6A4 4 0 0 1 15 7Zm1 1.5h.01",
  camera: "M3 8a2 2 0 0 1 2-2h2l2-2h6l2 2h2a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Zm9 9a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z",
  clock: "M12 7v5l3 2m7-2a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z",
  sun: "M12 3v2m0 14v2m9-9h-2M5 12H3m15.4-6.4-1.4 1.4M7 17l-1.4 1.4m12.8 0L17 17M7 7 5.6 5.6M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z",
  moon: "M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5Z",
  monitor: "M4 5h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Zm4 15h8m-4-3v3",
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  eye: "M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Zm10 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
  chart: "M4 20V10m6 10V4m6 16v-7m4 7H2",
  history: "M3 12a9 9 0 1 0 3-6.7L3 8m0-5v5h5m4-1v5l3 2",
  download: "M12 4v11m0 0-4-4m4 4 4-4M4 19h16",
  print: "M7 9V3h10v6M7 17H5a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-2m-10-3h10v7H7z",
  drop: "M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11Z",
  thermo: "M10 14.8V5a2 2 0 1 1 4 0v9.8a4 4 0 1 1-4 0ZM12 9v7",
  sparkle: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z",
  layers: "m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5",
};
export type IconName = keyof typeof paths;

export function Icon({ name, className = "h-5 w-5" }: { name: IconName; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={paths[name]} />
    </svg>
  );
}

/* ------------------------------------------------------------------ controls */

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";
const base =
  "inline-flex items-center justify-center gap-2 rounded-md font-medium whitespace-nowrap transition-colors duration-fast ease-out-quart disabled:cursor-not-allowed disabled:opacity-50";
const variants: Record<Variant, string> = {
  primary: "bg-primary text-on-primary shadow-xs hover:bg-primary-hover",
  secondary: "bg-surface text-ink ring-1 ring-inset ring-line-strong hover:bg-surface-2",
  ghost: "text-ink-2 hover:bg-surface-2 hover:text-ink",
  danger: "bg-surface text-danger-ink ring-1 ring-inset ring-danger/40 hover:bg-danger-soft",
};
const sizes: Record<Size, string> = {
  sm: "h-9 px-3 text-sm",
  md: "min-h-touch px-4 text-sm",
};

export function buttonClass(variant: Variant = "primary", size: Size = "md", className?: string) {
  return cx(base, variants[variant], sizes[size], className);
}

export function Button({
  variant = "primary",
  size = "md",
  className,
  busy,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size; busy?: boolean }) {
  return (
    <button {...props} disabled={props.disabled || busy} aria-busy={busy || undefined} className={buttonClass(variant, size, className)}>
      {busy && <Spinner />}
      {children}
    </button>
  );
}

export function LinkButton({ href, variant = "primary", size = "md", children, className }: {
  href: string; variant?: Variant; size?: Size; children: ReactNode; className?: string;
}) {
  return <Link href={href} className={buttonClass(variant, size, className)}>{children}</Link>;
}

export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={cx("animate-spin", className)} viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" fill="none" opacity="0.25" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" fill="none" />
    </svg>
  );
}

export function Field({ label, htmlFor, error, hint, children }: {
  label: string; htmlFor: string; error?: string; hint?: string; children: ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="block text-sm font-medium text-ink">{label}</label>
      {children}
      {hint && !error && <p id={`${htmlFor}-hint`} className="text-cap text-muted">{hint}</p>}
      {error && (
        <p id={`${htmlFor}-error`} role="alert" className="flex items-center gap-1 text-cap font-medium text-danger-ink">
          <Icon name="alert" className="h-3.5 w-3.5" /> {error}
        </p>
      )}
    </div>
  );
}

export const inputClass = (invalid?: boolean) =>
  cx(
    "block min-h-touch w-full rounded-md bg-surface px-3 text-base text-ink ring-1 ring-inset transition-shadow duration-fast",
    "placeholder:text-muted focus:outline-none focus:ring-2",
    invalid ? "ring-danger focus:ring-danger" : "ring-line-strong focus:ring-primary",
  );

export function Segmented<T extends string>({ value, options, onChange, label, size = "sm" }: {
  value: T; options: { value: T; label: string; icon?: IconName; disabled?: boolean }[]; onChange: (v: T) => void; label: string; size?: Size;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-md bg-surface-2 p-0.5 ring-1 ring-inset ring-line">
      {options.map((o) => (
        <button key={o.value} type="button" onClick={() => onChange(o.value)} aria-pressed={value === o.value} disabled={o.disabled}
          className={cx(
            "inline-flex items-center gap-1.5 rounded-sm px-2.5 font-medium transition-colors duration-fast",
            size === "sm" ? "h-8 text-cap" : "min-h-touch text-sm",
            value === o.value ? "bg-surface text-ink shadow-xs" : "text-muted hover:text-ink disabled:opacity-50 disabled:hover:text-muted",
          )}>
          {o.icon && <Icon name={o.icon} className="h-4 w-4" />}
          {o.label}
        </button>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ display */

type Tone = "neutral" | "primary" | "signal" | "warn" | "danger" | "info";
const tones: Record<Tone, string> = {
  neutral: "bg-surface-2 text-ink-2",
  primary: "bg-primary-soft text-primary-ink",
  signal: "bg-signal-soft text-signal-ink",
  warn: "bg-warn-soft text-warn-ink",
  danger: "bg-danger-soft text-danger-ink",
  info: "bg-info-soft text-info-ink",
};

export function Badge({ tone = "neutral", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={cx("inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-cap font-medium", tones[tone])}>
      {children}
    </span>
  );
}

export function Card({ children, className, title, action, id }: {
  children: ReactNode; className?: string; title?: ReactNode; action?: ReactNode; id?: string;
}) {
  return (
    <section id={id} className={cx("rounded-lg bg-surface shadow-xs ring-1 ring-line", className)}>
      {title && (
        <header className="flex min-h-12 items-center justify-between gap-3 px-5 pt-4">
          <h2 className="text-base font-semibold text-ink">{title}</h2>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function EmptyState({ icon = "leaf", title, children, action }: {
  icon?: IconName; title: string; children?: ReactNode; action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center px-6 py-10 text-center">
      <span className="mb-3 grid h-12 w-12 place-items-center rounded-full bg-primary-soft text-primary-ink">
        <Icon name={icon} />
      </span>
      <p className="font-medium text-ink">{title}</p>
      {children && <div className="mt-1 max-w-sm text-sm text-muted">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

type AlertTone = "danger" | "info" | "warn" | "success" | "signal";
const alertTone: Record<AlertTone, [string, IconName]> = {
  danger: ["bg-danger-soft text-danger-ink", "alert"],
  info: ["bg-info-soft text-info-ink", "info"],
  warn: ["bg-warn-soft text-warn-ink", "alert"],
  success: ["bg-primary-soft text-primary-ink", "check"],
  signal: ["bg-signal-soft text-signal-ink", "alert"],
};

export function Alert({ tone = "danger", children }: { tone?: AlertTone; children: ReactNode }) {
  const [cls, icon] = alertTone[tone];
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cx("flex gap-2.5 rounded-md px-3.5 py-3 text-sm", cls)}>
      <Icon name={icon} className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function PageHeader({ eyebrow, title, subtitle, actions }: {
  eyebrow?: ReactNode; title: ReactNode; subtitle?: ReactNode; actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <p className="mb-1 text-cap font-medium text-muted">{eyebrow}</p>}
        <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">{title}</h1>
        {subtitle && <p className="mt-1.5 max-w-reading text-base text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

/** Secondary figure: label above a tabular number. */
export function Stat({ label, value, hint, href }: { label: string; value: ReactNode; hint?: ReactNode; href?: string }) {
  const body = (
    <>
      <p className="text-cap text-muted">{label}</p>
      <p className="num mt-0.5 text-xl font-medium text-ink">{value}</p>
      {hint && <p className="mt-0.5 text-cap text-muted">{hint}</p>}
    </>
  );
  return href ? (
    <Link href={href} className="block rounded-md px-1 py-1 transition-colors duration-fast hover:bg-surface-2">{body}</Link>
  ) : (
    <div className="px-1 py-1">{body}</div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("animate-pulse rounded-md bg-surface-2", className)} aria-hidden="true" />;
}

/** One-tap choice between a few options (native radios styled as chips: arrow keys, labels and forms just work). */
export function ChipGroup<T extends string>({ legend, name, value, options, onChange, error, hideLegend = false }: {
  legend: string; name: string; value: T | ""; options: { value: T; label: string }[]; onChange: (v: T) => void; error?: string; hideLegend?: boolean;
}) {
  return (
    <fieldset aria-describedby={error ? `${name}-error` : undefined}>
      <legend className={cx("mb-1.5 text-sm font-medium text-ink", hideLegend && "sr-only")}>{legend}</legend>
      <div className="flex flex-wrap gap-1.5">
        {options.map((o) => (
          <label key={o.value}
            className={cx(
              "relative inline-flex min-h-9 cursor-pointer items-center rounded-full px-3 text-sm ring-1 ring-inset transition duration-fast",
              "has-focus-visible:shadow-glow",
              value === o.value ? "bg-primary text-on-primary ring-primary shadow-glow" : "bg-surface text-ink-2 ring-line-strong hover:text-ink",
            )}>
            <input type="radio" name={name} value={o.value} checked={value === o.value} onChange={() => onChange(o.value)} className="sr-only" />
            {o.label}
          </label>
        ))}
      </div>
      {error && (
        <p id={`${name}-error`} role="alert" className="mt-1.5 flex items-center gap-1 text-cap font-medium text-danger-ink">
          <Icon name="alert" className="h-3.5 w-3.5" /> {error}
        </p>
      )}
    </fieldset>
  );
}

export type MenuItem = { label: string; icon?: IconName; onSelect?: () => void; href?: string; tone?: "danger" };

/** Overflow menu for secondary actions (progressive disclosure): Esc closes, arrow keys move, focus returns. */
export function Menu({ label, items, icon = "menu" }: { label: string; items: MenuItem[]; icon?: IconName }) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    list.current?.querySelector<HTMLElement>("[role=menuitem]")?.focus();
    const close = (e: MouseEvent) => !list.current?.contains(e.target as Node) && !button.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  function onKey(e: React.KeyboardEvent) {
    const els = Array.from(list.current?.querySelectorAll<HTMLElement>("[role=menuitem]") ?? []);
    const i = els.indexOf(document.activeElement as HTMLElement);
    if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
      button.current?.focus();
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      els[(i + (e.key === "ArrowDown" ? 1 : -1) + els.length) % els.length]?.focus();
    }
  }
  const itemClass = (tone?: "danger") =>
    cx("flex min-h-10 w-full items-center gap-2.5 rounded-sm px-3 text-left text-sm transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus",
      tone === "danger" ? "text-danger-ink hover:bg-danger-soft focus:bg-danger-soft" : "text-ink hover:bg-surface-2 focus:bg-surface-2");
  return (
    <div className="relative">
      <button ref={button} type="button" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}
        className={buttonClass("secondary", "md", "px-3")}>
        <span className="sr-only">{label}</span>
        <Icon name={icon} className="h-4 w-4" />
      </button>
      {open && (
        <div ref={list} role="menu" aria-label={label} onKeyDown={onKey}
          className="absolute right-0 z-30 mt-1.5 w-64 animate-fade-up rounded-md bg-surface p-1 shadow-lg ring-1 ring-line">
          {items.map((it) =>
            it.href ? (
              <Link key={it.label} role="menuitem" href={it.href} className={itemClass(it.tone)} onClick={() => setOpen(false)}>
                {it.icon && <Icon name={it.icon} className="h-4 w-4 opacity-80" />}{it.label}
              </Link>
            ) : (
              <button key={it.label} role="menuitem" type="button" className={itemClass(it.tone)}
                onClick={() => { setOpen(false); it.onSelect?.(); }}>
                {it.icon && <Icon name={it.icon} className="h-4 w-4 opacity-80" />}{it.label}
              </button>
            ),
          )}
        </div>
      )}
    </div>
  );
}
