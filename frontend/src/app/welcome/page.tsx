import type { Metadata } from "next";
import Link from "next/link";
import { Reveal } from "@/components/reveal";
import { Icon, Logo, Mark, type IconName } from "@/components/ui";

/**
 * Public introduction, served at "/" to visitors without a session (see proxy.ts).
 * There is no public sign-up: accounts are issued by the municipality's administrator.
 */
export const metadata: Metadata = {
  title: { absolute: "Namaa · Green infrastructure management for Saudi municipalities" },
};

const STEPS: { title: string; body: string }[] = [
  { title: "Register green spaces", body: "Draw or import each park, garden and median, so every site has one record and one history." },
  { title: "Follow them from orbit", body: "Sentinel-2 builds a vegetation and moisture timeline for each site, compared with its own seasonal pattern." },
  { title: "Review what changed", body: "Unusual declines reach an attention queue with the evidence. A manager decides; the satellite only points." },
  { title: "Act and record", body: "Decisions become inspection or maintenance tasks, and field findings stay with the site." },
];

const ROLES: { icon: IconName; title: string; body: string }[] = [
  { icon: "clipboard", title: "Municipal managers", body: "Review the attention queue, decide and assign work." },
  { icon: "check", title: "Field inspectors", body: "Visit sites and record findings with photos and notes." },
  { icon: "eye", title: "Viewers", body: "Follow green-space condition and read reports." },
  { icon: "users", title: "Administrators", body: "Issue accounts, set roles and review activity." },
];

const CONTEXT: { icon: IconName; label: string }[] = [
  { icon: "drop", label: "Estimated water demand (FAO-56)" },
  { icon: "thermo", label: "Land-surface heat context" },
  { icon: "chart", label: "Printable site and city reports" },
];

const btn = "group inline-flex min-h-12 items-center justify-center gap-2 rounded-lg px-6 text-base font-medium transition duration-base ease-out focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";
const btnPrimary = `${btn} bg-primary text-on-primary shadow-sm hover:bg-primary-hover hover:shadow-glow`;

function Arrow() {
  return <Icon name="arrow" className="h-4 w-4 transition-transform duration-base ease-out group-hover:translate-x-0.5" />;
}

/** Animated illustration: sites appear, a satellite pass sweeps across, one site is flagged. Not live data. */
function OrbitPanel() {
  return (
    <div className="welcome-rise relative aspect-[5/4] [container-type:inline-size] w-full overflow-hidden rounded-2xl border border-line bg-surface shadow-lg" style={{ animationDelay: "120ms" }} aria-hidden="true">
      <svg className="absolute inset-0 h-full w-full text-line">
        <defs>
          <pattern id="welcome-grid" width="32" height="32" patternUnits="userSpaceOnUse">
            <path d="M32 0H0v32" fill="none" stroke="currentColor" strokeWidth="1" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#welcome-grid)" />
      </svg>
      <svg viewBox="0 0 500 400" className="absolute inset-0 h-full w-full">
        <g className="welcome-site" style={{ animationDelay: "300ms" }}>
          <path d="M60 70 190 40l45 100-130 45Z" fill="var(--c-ndvi-4)" fillOpacity="0.5" stroke="var(--c-map-outline)" strokeWidth="1.5" />
        </g>
        <g className="welcome-site" style={{ animationDelay: "420ms" }}>
          <path d="M290 50h140v100l-85 35-55-60Z" fill="var(--c-ndvi-5)" fillOpacity="0.5" stroke="var(--c-map-outline)" strokeWidth="1.5" />
        </g>
        <g className="welcome-site" style={{ animationDelay: "540ms" }}>
          <path d="M140 195 205 180l20 50-70 18Z" fill="var(--c-ndvi-3)" fillOpacity="0.5" stroke="var(--c-map-outline)" strokeWidth="1.5" />
        </g>
        <g className="welcome-site" style={{ animationDelay: "660ms" }}>
          <path d="M250 215 370 195l35 95-135 25Z" fill="var(--c-ndvi-2)" fillOpacity="0.85" stroke="var(--c-map-outline)" strokeWidth="1.5" />
          <path className="welcome-flag" d="M250 215 370 195l35 95-135 25Z" fill="none" stroke="var(--c-map-highlight)" strokeWidth="3" pathLength="1" />
        </g>
        <circle className="welcome-ping" cx="328" cy="258" r="18" fill="none" stroke="var(--c-signal)" strokeWidth="2" />
        <circle className="welcome-site" style={{ animationDelay: "1500ms" }} cx="328" cy="258" r="6" fill="var(--c-signal)" />
      </svg>
      <div className="welcome-scan absolute inset-y-0 left-0 w-24" />
      <div className="glass welcome-rise absolute right-4 top-4 flex items-center gap-2 rounded-full px-3 py-1.5 text-cap font-medium text-ink-2" style={{ animationDelay: "500ms" }}>
        <Icon name="satellite" className="h-4 w-4 text-primary-ink" /> Sentinel-2 pass · 10 m
      </div>
      <div className="glass welcome-rise absolute bottom-3 left-3 max-w-[13rem] rounded-xl p-3 sm:bottom-4 sm:left-4 sm:max-w-[15rem] sm:p-4" style={{ animationDelay: "1700ms" }}>
        <p className="flex items-center gap-1.5 text-cap font-medium text-signal-ink">
          <span className="h-2 w-2 rounded-full bg-signal" /> Needs attention
        </p>
        <p className="mt-1 font-semibold text-ink">Neighbourhood garden</p>
        <p className="mt-1 hidden text-sm text-ink-2 sm:block">Vegetation below its usual level for this time of year.</p>
      </div>
      <p className="absolute bottom-3 right-4 text-cap text-muted">Illustration</p>
    </div>
  );
}

export default function WelcomePage() {
  return (
    <div className="fluid-type min-h-screen bg-canvas text-ink">
      <noscript><style>{"[data-reveal]{opacity:1!important;transform:none!important}"}</style></noscript>

      <header className="sticky top-0 z-20 border-b border-line bg-[var(--c-glass)] backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-8">
          <Link href="/" aria-label="Namaa home"><Logo /></Link>
          <nav aria-label="Main" className="flex items-center gap-2 sm:gap-6">
            <a href="#how-it-works" className="hidden text-sm font-medium text-ink-2 transition-colors duration-fast hover:text-ink sm:inline">How it works</a>
            <a href="#roles" className="hidden text-sm font-medium text-ink-2 transition-colors duration-fast hover:text-ink sm:inline">Who it&apos;s for</a>
            <Link href="/login" className="inline-flex h-10 items-center rounded-lg bg-primary px-4 text-sm font-medium text-on-primary shadow-sm transition duration-base ease-out hover:bg-primary-hover hover:shadow-glow focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus">Sign in</Link>
          </nav>
        </div>
      </header>

      <main>
        {/* Hero */}
        <section className="relative overflow-hidden" aria-labelledby="welcome-title">
          <div className="pointer-events-none absolute -right-48 -top-48 h-[36rem] w-[36rem] text-primary opacity-[0.07]" aria-hidden="true">
            <Mark className="h-full w-full" />
          </div>
          <div className="relative mx-auto grid max-w-7xl items-center gap-12 px-4 py-16 sm:px-8 lg:min-h-[calc(100dvh-4rem)] lg:grid-cols-[1.05fr_1fr] lg:gap-16 lg:py-20">
            <div>
              <p className="welcome-rise inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 text-sm font-medium text-primary-ink">
                <span className="h-1.5 w-1.5 rounded-full bg-primary" /> Riyadh pilot · Copernicus Sentinel-2
              </p>
              <h1 id="welcome-title" className="welcome-rise mt-6 text-[clamp(2.5rem,4.4vw,4rem)] font-semibold leading-[1.02] tracking-[-0.035em]" style={{ animationDelay: "60ms" }}>
                See which green spaces need attention, <span className="text-primary-ink">and why.</span>
              </h1>
              <p className="welcome-rise mt-6 max-w-xl text-xl leading-relaxed text-ink-2" style={{ animationDelay: "120ms" }}>
                Namaa keeps a satellite condition history for every public park, garden and median, so municipal teams know
                where to look and keep a record of the work that follows.
              </p>
              <div className="welcome-rise mt-10 flex flex-wrap items-center gap-x-6 gap-y-4" style={{ animationDelay: "180ms" }}>
                <Link href="/login" className={btnPrimary}>Sign in <Arrow /></Link>
                <a href="#how-it-works" className="group inline-flex items-center gap-2 text-base font-medium text-ink-2 transition-colors duration-fast hover:text-ink">
                  See how it works <Icon name="forward" className="h-4 w-4 rotate-90 transition-transform duration-base ease-out group-hover:translate-y-0.5" />
                </a>
              </div>
            </div>
            <OrbitPanel />
          </div>
        </section>

        {/* How it works */}
        <section id="how-it-works" className="scroll-mt-16 border-y border-line bg-surface" aria-labelledby="how-title">
          <div className="mx-auto max-w-7xl px-4 py-20 sm:px-8 lg:py-28">
            <Reveal>
              <p className="text-sm font-medium uppercase tracking-[0.14em] text-primary-ink">How it works</p>
              <h2 id="how-title" className="mt-3 max-w-2xl text-[clamp(2rem,3.4vw,2.75rem)] font-semibold leading-tight tracking-[-0.025em]">
                From satellite signal to field action
              </h2>
            </Reveal>
            <div className="relative mt-14">
            <Reveal className="welcome-track pointer-events-none absolute left-5 right-5 top-5 hidden h-px lg:block" />
            <ol className="relative grid gap-10 sm:grid-cols-2 lg:grid-cols-4 lg:gap-10">
              {STEPS.map((s, i) => (
                <Reveal as="li" key={s.title} delay={i * 90} className="relative">
                  <span className="relative grid h-10 w-10 place-items-center rounded-full border border-primary/30 bg-primary-soft font-mono text-sm font-medium text-primary-ink" aria-hidden="true">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <h3 className="mt-6 text-xl font-semibold tracking-tight">{s.title}</h3>
                  <p className="mt-3 text-lg leading-relaxed text-ink-2">{s.body}</p>
                </Reveal>
              ))}
            </ol>
            </div>
            <Reveal className="mt-16 flex flex-wrap gap-3" delay={120}>
              {CONTEXT.map((c) => (
                <span key={c.label} className="inline-flex items-center gap-2 rounded-full border border-line bg-canvas px-4 py-2 text-sm font-medium text-ink-2">
                  <Icon name={c.icon} className="h-4 w-4 text-primary-ink" /> {c.label}
                </span>
              ))}
            </Reveal>
          </div>
        </section>

        {/* Roles */}
        <section id="roles" className="scroll-mt-16" aria-labelledby="roles-title">
          <div className="mx-auto grid max-w-7xl gap-12 px-4 py-20 sm:px-8 lg:grid-cols-[1fr_1.4fr] lg:gap-20 lg:py-28">
            <Reveal>
              <p className="text-sm font-medium uppercase tracking-[0.14em] text-primary-ink">Who it&apos;s for</p>
              <h2 id="roles-title" className="mt-3 text-[clamp(2rem,3.4vw,2.75rem)] font-semibold leading-tight tracking-[-0.025em]">
                One workspace for everyone who looks after the city&apos;s green spaces
              </h2>
              <p className="mt-5 text-lg leading-relaxed text-ink-2">Everyone signs in at the same place. What you see depends on the role your administrator gives you.</p>
            </Reveal>
            <ul className="grid gap-4 sm:grid-cols-2">
              {ROLES.map((r, i) => (
                <Reveal as="li" key={r.title} delay={i * 80}
                  className="rounded-2xl border border-line bg-surface p-6 transition duration-base ease-out hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md">
                  <span className="grid h-11 w-11 place-items-center rounded-xl bg-primary-soft text-primary-ink"><Icon name={r.icon} /></span>
                  <h3 className="mt-5 text-lg font-semibold">{r.title}</h3>
                  <p className="mt-2 text-base leading-relaxed text-ink-2">{r.body}</p>
                </Reveal>
              ))}
            </ul>
          </div>
        </section>

        {/* Sign-in band */}
        <section className="px-4 pb-20 sm:px-8 lg:pb-28" aria-labelledby="cta-title">
          <Reveal className="relative mx-auto max-w-7xl overflow-hidden rounded-3xl bg-primary px-6 py-14 text-on-primary sm:px-12 lg:py-16">
            <div className="pointer-events-none absolute -bottom-32 -right-24 h-96 w-96 opacity-15" aria-hidden="true"><Mark className="h-full w-full" /></div>
            <div className="relative flex flex-col gap-8 lg:flex-row lg:items-center lg:justify-between">
              <div className="max-w-2xl">
                <h2 id="cta-title" className="text-[clamp(1.75rem,3vw,2.5rem)] font-semibold leading-tight tracking-[-0.02em]">Ready when you are</h2>
                <p className="mt-3 text-lg opacity-90">
                  Sign in with the account your municipality gave you. Namaa has no public sign-up; new accounts are created by a Namaa administrator.
                </p>
              </div>
              <Link href="/login" className={`${btn} shrink-0 bg-surface text-primary-ink shadow-md hover:-translate-y-0.5 hover:shadow-lg`}>
                Sign in to Namaa <Arrow />
              </Link>
            </div>
          </Reveal>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-8 text-sm text-muted sm:px-8 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-3">
            <Mark className="h-6 w-6 shrink-0 text-primary-ink" />
            <p>Namaa is a capstone project at Prince Sultan University, supervised by Dr. Amani Almalki.</p>
          </div>
          <p>Contains modified Copernicus Sentinel data · © OpenStreetMap contributors</p>
        </div>
      </footer>
    </div>
  );
}
