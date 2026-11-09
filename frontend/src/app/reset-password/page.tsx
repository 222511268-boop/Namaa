"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";
import { Alert, Button, buttonClass, Field, inputClass, Logo, Spinner } from "@/components/ui";
import { api, ApiError, errorMessage } from "@/lib/api";

function ResetForm() {
  const token = useSearchParams().get("token") ?? "";
  const [state, setState] = useState<"checking" | "valid" | "invalid" | "done">(token ? "checking" : "invalid");
  const [name, setName] = useState("");
  const [message, setMessage] = useState("This reset link is invalid or has expired. Ask your administrator for a new one.");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) return;
    api<{ full_name: string }>("/api/auth/reset-password/check", { method: "POST", json: { token } })
      .then((r) => {
        setName(r.full_name);
        setState("valid");
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 400) setMessage(e.message);
        setState("invalid");
      });
  }, [token]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const local: Record<string, string> = {};
    if (password.length < 10) local.new_password = "Use at least 10 characters.";
    else if (password !== confirm) local.confirm = "The two passwords do not match.";
    setErrors(local);
    if (Object.keys(local).length) return;
    setBusy(true);
    try {
      await api("/api/auth/reset-password", { method: "POST", json: { token, new_password: password } });
      setState("done");
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fieldErrors).length) setErrors(err.fieldErrors);
      else if (err instanceof ApiError && err.status === 400) {
        setMessage(err.message);
        setState("invalid");
      } else setErrors({ form: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  }

  if (state === "checking") return <div className="flex justify-center py-8 text-muted"><Spinner className="h-5 w-5" /></div>;
  if (state === "invalid")
    return (
      <div className="space-y-4">
        <Alert>{message}</Alert>
        <Link href="/login" className="text-sm font-medium text-primary-ink underline underline-offset-4">Back to sign in</Link>
      </div>
    );
  if (state === "done")
    return (
      <div className="space-y-4">
        <Alert tone="success">Your password has been changed. Any previous sessions have been signed out.</Alert>
        <Link href="/login" className={buttonClass()}>Sign in</Link>
      </div>
    );
  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      <p className="text-sm text-ink-2">Choose a new password for <strong>{name}</strong>.</p>
      {errors.form && <Alert>{errors.form}</Alert>}
      <Field label="New password" htmlFor="new-password" error={errors.new_password} hint="At least 10 characters.">
        <input id="new-password" type="password" autoComplete="new-password" value={password}
          onChange={(e) => setPassword(e.target.value)} className={inputClass(!!errors.new_password)} />
      </Field>
      <Field label="Repeat new password" htmlFor="confirm-password" error={errors.confirm}>
        <input id="confirm-password" type="password" autoComplete="new-password" value={confirm}
          onChange={(e) => setConfirm(e.target.value)} className={inputClass(!!errors.confirm)} />
      </Field>
      <Button type="submit" busy={busy} className="w-full">Set new password</Button>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <div className="flex min-h-screen items-center justify-center px-6 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-10"><Logo /></div>
        <h1 className="mb-4 text-3xl font-semibold tracking-tight text-ink">Reset password</h1>
        <Suspense>
          <ResetForm />
        </Suspense>
      </div>
    </div>
  );
}
