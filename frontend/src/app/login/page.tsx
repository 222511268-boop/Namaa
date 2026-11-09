"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState, useSyncExternalStore, type FormEvent } from "react";
import { Alert, Button, Field, Icon, inputClass, Logo, Mark } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

function safeNext(next: string | null): string {
  // Only allow same-site relative paths to avoid open redirects.
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

/** Shown only after an expired session redirect; kept out of the form so the form never waits on search params. */
function ExpiredNotice() {
  return useSearchParams().get("expired") ? <Alert tone="info">Your session has ended. Please sign in again.</Alert> : null;
}

// The last email used on this device (never the password), so returning users only type their password.
const EMAIL_KEY = "namaa-last-email";
const readRemembered = () => {
  try {
    return localStorage.getItem(EMAIL_KEY) ?? "";
  } catch {
    return "";
  }
};
const noSubscribe = () => () => undefined;

function LoginForm() {
  const remembered = useSyncExternalStore(noSubscribe, readRemembered, () => "");
  const [typed, setTyped] = useState<string | null>(null);
  const email = typed ?? remembered;
  const setEmail = setTyped;
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    (remembered ? passwordRef : emailRef).current?.focus();
  }, [remembered]);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!email.trim() || !password) {
      setError("Enter your email and password.");
      return;
    }
    setBusy(true);
    try {
      await api("/api/auth/login", { method: "POST", json: { email, password } });
      try {
        localStorage.setItem(EMAIL_KEY, email.trim());
      } catch {
        /* storage unavailable */
      }
      setPassword("");
      // Full navigation, not router.replace: while signed out, "/" was served (and may be cached client-side)
      // as the public landing page, so the signed-in page must be fetched fresh with the new session cookie.
      window.location.replace(safeNext(new URLSearchParams(window.location.search).get("next")));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign-in failed. Please try again.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-5">
      {!error && <Suspense><ExpiredNotice /></Suspense>}
      {error && <Alert>{error}</Alert>}
      <Field label="Email" htmlFor="email">
        <input ref={emailRef} id="email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)}
          className={inputClass(!!error)} aria-invalid={!!error || undefined} />
      </Field>
      <Field label="Password" htmlFor="password">
        <input ref={passwordRef} id="password" type="password" autoComplete="current-password" value={password}
          onChange={(e) => setPassword(e.target.value)} className={inputClass(!!error)} aria-invalid={!!error || undefined} />
      </Field>
      <Button type="submit" busy={busy} className="w-full">Sign in</Button>
      {remembered && typed === null ? (
        <p className="text-cap text-muted">
          Not you?{" "}
          <button type="button" className="font-medium text-primary-ink underline underline-offset-4"
            onClick={() => {
              try {
                localStorage.removeItem(EMAIL_KEY);
              } catch {
                /* storage unavailable */
              }
              setTyped("");
              emailRef.current?.focus();
            }}>
            Use another account
          </button>
        </p>
      ) : (
        <p className="text-cap text-muted">
          One sign-in for every role. If you need an account or a password reset, ask a Namaa administrator in your
          municipality.
        </p>
      )}
    </form>
  );
}

/** Decorative instrument panel: hairline grid, orbit and the three steps of the product loop. */
function Hero() {
  return (
    <section className="relative hidden overflow-hidden border-r border-line bg-surface lg:block" aria-hidden="true">
      <svg className="absolute inset-0 h-full w-full text-line" aria-hidden="true">
        <defs>
          <pattern id="login-grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M40 0H0v40" fill="none" stroke="currentColor" strokeWidth="1" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#login-grid)" />
      </svg>
      <div className="absolute -right-48 top-1/2 h-96 w-96 -translate-y-1/2 text-primary opacity-25">
        <Mark className="h-full w-full" />
      </div>
      <div className="relative flex h-full flex-col justify-between p-12">
        <Logo />
        <div className="max-w-md">
          <p className="text-cap font-medium text-primary-ink">Riyadh pilot · Sentinel-2</p>
          <p className="mt-3 text-display font-semibold tracking-tight text-ink">From satellite signal to field action.</p>
          <p className="mt-5 text-lg text-ink-2">
            Namaa keeps a condition history for every public green space, so municipal teams can see where attention is
            needed and record the work that follows.
          </p>
        </div>
        <p className="text-cap text-muted">Contains modified Copernicus Sentinel data · OpenStreetMap contributors</p>
      </div>
    </section>
  );
}

export default function LoginPage() {
  return (
    <div className="fluid-type grid min-h-screen lg:grid-cols-2">
      <Hero />
      <section className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-10 lg:hidden"><Logo /></div>
          <Link href="/" className="mb-6 inline-flex items-center gap-1 text-cap font-medium text-primary-ink underline-offset-4 hover:underline">
            <Icon name="back" className="h-4 w-4" /> About Namaa
          </Link>
          <h1 className="text-3xl font-semibold tracking-tight text-ink">Sign in</h1>
          <p className="mb-8 mt-1.5 text-base text-muted">Use the account provided by your municipality.</p>
          <LoginForm />
        </div>
      </section>
    </div>
  );
}
