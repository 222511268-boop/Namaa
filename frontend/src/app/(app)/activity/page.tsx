"use client";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import type { ActivityEvent, User } from "@/lib/types";
import { useUser } from "@/components/session";
import { Alert, Button, Field, inputClass, PageHeader } from "@/components/ui";

export default function ActivityPage() {
  const user = useUser();
  const [actions, setActions] = useState<{ action: string; label: string }[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [action, setAction] = useState("");
  const [actor, setActor] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<{ total: number; items: ActivityEvent[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const query = new URLSearchParams({ offset: String(offset), limit: "50", ...(action ? { action } : {}), ...(actor ? { user_id: actor } : {}), ...(start ? { start } : {}), ...(end ? { end } : {}), ...(q ? { q } : {}) }).toString();
  useEffect(() => {
    if (user.role !== "admin") return;
    api<typeof actions>("/api/activity/actions").then(setActions).catch(() => undefined);
    api<User[]>("/api/users").then(setUsers).catch(() => undefined);
  }, [user.role]);
  useEffect(() => {
    if (user.role !== "admin") return;
    let stale = false;
    api<typeof data>(`/api/activity?${query}`).then(result => { if (!stale) { setData(result); setError(null); } }).catch(e => { if (!stale) setError(errorMessage(e)); });
    return () => { stale = true; };
  }, [query, user.role]);
  if (user.role !== "admin") return <Alert>Only administrators can view activity records.</Alert>;
  return <div className="mx-auto max-w-content space-y-5 px-4 py-6 sm:px-6">
    <PageHeader title="Activity record" eyebrow="Administration" />
    <p className="text-sm text-muted">Read-only history of account, site, review, task and processing actions. Times are displayed in your local time zone.</p>
    <div className="flex flex-wrap gap-3">
      <Field label="Action" htmlFor="activity-action"><select id="activity-action" className={inputClass()} value={action} onChange={e => { setAction(e.target.value); setOffset(0); }}><option value="">All actions</option>{actions.map(a => <option key={a.action} value={a.action}>{a.label}</option>)}</select></Field>
      <Field label="User" htmlFor="activity-user"><select id="activity-user" className={inputClass()} value={actor} onChange={e => { setActor(e.target.value); setOffset(0); }}><option value="">All users</option>{users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select></Field>
      <Field label="From" htmlFor="activity-start"><input id="activity-start" type="date" value={start} className={inputClass()} onChange={e => { setStart(e.target.value); setOffset(0); }} /></Field>
      <Field label="Through" htmlFor="activity-end"><input id="activity-end" type="date" value={end} min={start} className={inputClass()} onChange={e => { setEnd(e.target.value); setOffset(0); }} /></Field>
      <Field label="Search records" htmlFor="activity-search"><input id="activity-search" type="search" maxLength={120} value={q} className={inputClass()} onChange={e => { setQ(e.target.value); setOffset(0); }} /></Field>
    </div>
    {error && <Alert>{error}</Alert>}
    {data && <><p className="num text-sm text-muted">{data.total} matching records</p><div className="overflow-x-auto rounded-md ring-1 ring-line"><table className="w-full text-left text-sm">
      <thead><tr>{["Time", "User / role", "Action", "Record"].map(h => <th key={h} className="p-3">{h}</th>)}</tr></thead>
      <tbody>{data.items.map(e => <tr key={e.id} className="border-t border-line align-top"><td className="whitespace-nowrap p-3">{new Date(e.at).toLocaleString()}</td><td className="p-3">{e.user_name ?? "System"}<span className="block text-cap text-muted">{e.user_role}</span></td><td className="p-3">{e.action_label}</td><td className="p-3">{e.summary}<details className="mt-1 text-cap"><summary className="cursor-pointer text-muted">Details</summary><pre className="max-w-lg overflow-auto whitespace-pre-wrap">{JSON.stringify(e.details, null, 2)}</pre></details></td></tr>)}</tbody>
    </table>{data.items.length === 0 && <p className="p-4 text-muted">No matching activity.</p>}</div>
      <div className="flex gap-3"><Button variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</Button><Button variant="secondary" disabled={offset + 50 >= data.total} onClick={() => setOffset(offset + 50)}>Next</Button></div></>}
  </div>;
}
