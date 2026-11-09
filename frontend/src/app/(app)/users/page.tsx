"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { RequireRole } from "@/components/app-shell";
import { useUser } from "@/components/session";
import { useToast } from "@/components/toast";
import { Alert, Badge, Button, Card, ChipGroup, Field, Icon, inputClass, PageHeader, Spinner } from "@/components/ui";
import { api, ApiError, errorMessage } from "@/lib/api";
import { formatDate, formatDateTime, ROLE_LABEL } from "@/lib/format";
import { can } from "@/lib/permissions";
import type { Role, User } from "@/lib/types";
import { useMediaQuery, WIDE } from "@/lib/use-media";

const ROLES = Object.keys(ROLE_LABEL) as Role[];

/** A strong initial password (14 characters, no look-alike letters), generated in the browser. */
function generatePassword(): string {
  const alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const bytes = crypto.getRandomValues(new Uint8Array(14));
  return Array.from(bytes, (b) => alphabet[b % alphabet.length]).join("");
}

async function copy(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export default function UsersPage() {
  const me = useUser();
  const toast = useToast();
  const [users, setUsers] = useState<User[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rowBusy, setRowBusy] = useState<string | null>(null);
  const [resetLink, setResetLink] = useState<{ name: string; url: string; expires_at: string } | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(() => {
    api<User[]>("/api/users").then(setUsers).catch((e) => setError(errorMessage(e)));
  }, []);
  useEffect(load, [load]);

  async function update(u: User, patch: Partial<Pick<User, "role" | "is_active">>) {
    setRowBusy(u.id);
    setError(null);
    try {
      const saved = await api<User>(`/api/users/${u.id}`, { method: "PATCH", json: patch });
      setUsers((list) => list?.map((x) => (x.id === saved.id ? saved : x)) ?? null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setRowBusy(null);
    }
  }

  async function issueLink(u: User) {
    setRowBusy(u.id);
    setError(null);
    setCopied(false);
    try {
      const r = await api<{ url: string; expires_at: string }>(`/api/users/${u.id}/reset-link`, { method: "POST" });
      setResetLink({ name: u.full_name, ...r });
      // The link is meant to be shared, so it goes straight to the clipboard.
      const ok = await copy(r.url);
      setCopied(ok);
      toast(ok ? { tone: "success", text: `Reset link for ${u.full_name} copied.` } : { tone: "info", text: "Reset link ready: copy it from the panel." });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setRowBusy(null);
    }
  }

  return (
    <RequireRole allowed={can.manageUsers}>
      <div className="mx-auto max-w-content px-4 py-6 sm:px-6 sm:py-8">
        <PageHeader title="Users" subtitle="Create accounts and choose what each person can do." />
        <div className="grid gap-6 lg:grid-cols-3">
          <Card title="Accounts" className="min-w-0 lg:col-span-2">
            {error && <div className="p-4"><Alert>{error}</Alert></div>}
            {resetLink && (
              <div className="border-b border-line p-4" data-testid="reset-link-panel">
                <Alert tone="info">
                  <p className="font-medium">Password reset link for {resetLink.name}</p>
                  <p className="mt-1">Give this link to the user through a trusted channel. It works once and expires{" "}
                    {formatDateTime(resetLink.expires_at)}. It will not be shown again.</p>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <input readOnly value={resetLink.url} aria-label="Reset link" data-testid="reset-link"
                      className="num min-h-9 min-w-0 flex-1 rounded-sm bg-surface px-2 text-cap text-ink ring-1 ring-inset ring-line-strong"
                      onFocus={(e) => e.target.select()} />
                    <Button variant="secondary" size="sm" onClick={() => navigator.clipboard?.writeText(resetLink.url).then(() => setCopied(true))}>
                      {copied ? "Copied" : "Copy"}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => setResetLink(null)}>Done</Button>
                  </div>
                </Alert>
              </div>
            )}
            {!users && !error && <div className="flex justify-center py-10 text-muted"><Spinner /></div>}
            {users && (
              <div>
                <table className="w-full text-left text-sm" data-testid="user-table">
                  <thead className="text-cap text-muted max-sm:sr-only">
                    <tr className="border-b border-line">
                      <th scope="col" className="px-5 py-2.5 font-medium">Name</th>
                      <th scope="col" className="px-3 py-2.5 font-medium">Role</th>
                      <th scope="col" className="px-3 py-2.5 font-medium">Status</th>
                      <th scope="col" className="px-5 py-2.5"><span className="sr-only">Actions</span></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line max-sm:block">
                    {users.map((u) => (
                      <tr key={u.id} data-email={u.email} className="max-sm:grid max-sm:grid-cols-2 max-sm:items-center max-sm:gap-3 max-sm:px-4 max-sm:py-4">
                        <td className="px-5 py-3 max-sm:col-span-2 max-sm:p-0">
                          <p className="font-medium text-ink">{u.full_name}{u.id === me.id && <span className="text-muted"> (you)</span>}</p>
                          <p className="text-cap text-muted">{u.email} · since {formatDate(u.created_at)}</p>
                        </td>
                        <td className="px-3 py-3 max-sm:p-0">
                          <label className="sr-only" htmlFor={`role-${u.id}`}>Role for {u.full_name}</label>
                          <select id={`role-${u.id}`} value={u.role} disabled={u.id === me.id || rowBusy === u.id}
                            onChange={(e) => update(u, { role: e.target.value as Role })} className={inputClass()}>
                            {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                          </select>
                        </td>
                        <td className="px-3 py-3 max-sm:p-0">{u.is_active ? <Badge tone="primary">Active</Badge> : <Badge tone="danger">Deactivated</Badge>}</td>
                        <td className="whitespace-nowrap px-5 py-3 text-right max-sm:col-span-2 max-sm:p-0 max-sm:text-left">
                          {u.id !== me.id && u.is_active && (
                            <Button variant="ghost" size="sm" className="me-1" disabled={rowBusy === u.id} onClick={() => issueLink(u)}>
                              Reset link
                            </Button>
                          )}
                          {u.id !== me.id && (
                            <Button variant={u.is_active ? "danger" : "secondary"} size="sm" busy={rowBusy === u.id}
                              onClick={() => update(u, { is_active: !u.is_active })}>
                              {u.is_active ? "Deactivate" : "Reactivate"}
                            </Button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
          <NewUserForm onCreated={load} />
        </div>
      </div>
    </RequireRole>
  );
}

function NewUserForm({ onCreated }: { onCreated: () => void }) {
  const [form, setForm] = useState(() => ({ full_name: "", email: "", role: "viewer" as Role, password: generatePassword() }));
  const wide = useMediaQuery(WIDE);
  const nameRef = useRef<HTMLInputElement>(null);
  // Desktop, or arriving from "Create a user account" in the palette: start typing the name straight away.
  useEffect(() => {
    if (wide || window.location.hash === "#new") nameRef.current?.focus();
  }, [wide]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => {
    const value = e.target.value;
    setForm(previous => ({ ...previous, [k]: value }));
  };

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErrors({});
    setDone(null);
    const local: Record<string, string> = {};
    if (form.full_name.trim().length < 2) local.full_name = "Enter the person's full name.";
    if (!/^\S+@\S+\.\S+$/.test(form.email.trim())) local.email = "Enter a valid email address.";
    if (form.password.length < 10) local.password = "Use at least 10 characters.";
    if (Object.keys(local).length) return setErrors(local);
    setBusy(true);
    try {
      const u = await api<User>("/api/users", { method: "POST", json: form });
      const copied = await copy(form.password);
      setDone(`Account created for ${u.full_name}. ${copied ? "The initial password is on your clipboard" : "Copy the initial password"}; share it with them securely.`);
      setForm({ full_name: "", email: "", role: "viewer", password: generatePassword() });
      nameRef.current?.focus();
      onCreated();
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fieldErrors).length) setErrors(err.fieldErrors);
      else setErrors({ form: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Create an account">
      <form onSubmit={submit} noValidate className="space-y-4 p-5">
        {errors.form && <Alert>{errors.form}</Alert>}
        {done && <Alert tone="success">{done}</Alert>}
        <Field label="Full name" htmlFor="full_name" error={errors.full_name}>
          <input ref={nameRef} id="full_name" value={form.full_name} onChange={set("full_name")} className={inputClass(!!errors.full_name)} aria-invalid={!!errors.full_name || undefined} />
        </Field>
        <Field label="Email" htmlFor="new-email" error={errors.email}>
          <input id="new-email" type="email" value={form.email} onChange={set("email")} className={inputClass(!!errors.email)} aria-invalid={!!errors.email || undefined} />
        </Field>
        <ChipGroup legend="Role" name="new-role" value={form.role} onChange={(role) => setForm(previous => ({ ...previous, role }))} error={errors.role}
          options={ROLES.map((r) => ({ value: r, label: ROLE_LABEL[r] }))} />
        <Field label="Initial password" htmlFor="new-password" error={errors.password} hint="Generated for you; copied when the account is created.">
          <div className="flex gap-2">
            <input id="new-password" type="text" autoComplete="off" spellCheck={false} value={form.password} onChange={set("password")}
              className={inputClass(!!errors.password) + " num"} aria-invalid={!!errors.password || undefined} />
            <Button type="button" variant="ghost" className="px-3" onClick={() => { const password = generatePassword(); setForm(previous => ({ ...previous, password })); }}>
              <Icon name="refresh" className="h-4 w-4" /><span className="sr-only">Generate another password</span>
            </Button>
          </div>
        </Field>
        <Button type="submit" busy={busy}>Create account</Button>
      </form>
    </Card>
  );
}
