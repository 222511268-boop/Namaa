"use client";

import { useState, type FormEvent } from "react";
import { useUser } from "@/components/session";
import { Alert, Button, Card, Field, inputClass, PageHeader } from "@/components/ui";
import { api, ApiError, errorMessage } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/format";

export default function AccountPage() {
  const user = useUser();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setDone(false);
    const local: Record<string, string> = {};
    if (!current) local.current_password = "Enter your current password.";
    if (next.length < 10) local.new_password = "Use at least 10 characters.";
    else if (next !== confirm) local.confirm = "The two new passwords do not match.";
    setErrors(local);
    if (Object.keys(local).length) return;
    setBusy(true);
    try {
      await api("/api/auth/change-password", { method: "POST", json: { current_password: current, new_password: next } });
      setDone(true);
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      setErrors(err instanceof ApiError && Object.keys(err.fieldErrors).length ? err.fieldErrors : { form: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-6 sm:px-6 sm:py-8">
      <PageHeader title="Account" subtitle={`${user.full_name} · ${user.email} · ${ROLE_LABEL[user.role]}`} />
      <Card title="Change password">
        <form onSubmit={submit} noValidate className="space-y-4 p-5">
          {errors.form && <Alert>{errors.form}</Alert>}
          {done && <Alert tone="success">Password changed. You stay signed in here; other devices have been signed out.</Alert>}
          <Field label="Current password" htmlFor="current-password" error={errors.current_password}>
            <input id="current-password" type="password" autoComplete="current-password" value={current}
              onChange={(e) => setCurrent(e.target.value)} className={inputClass(!!errors.current_password)} />
          </Field>
          <Field label="New password" htmlFor="new-password" error={errors.new_password} hint="At least 10 characters.">
            <input id="new-password" type="password" autoComplete="new-password" value={next}
              onChange={(e) => setNext(e.target.value)} className={inputClass(!!errors.new_password)} />
          </Field>
          <Field label="Repeat new password" htmlFor="confirm-password" error={errors.confirm}>
            <input id="confirm-password" type="password" autoComplete="new-password" value={confirm}
              onChange={(e) => setConfirm(e.target.value)} className={inputClass(!!errors.confirm)} />
          </Field>
          <Button type="submit" busy={busy}>Change password</Button>
        </form>
      </Card>
    </div>
  );
}
