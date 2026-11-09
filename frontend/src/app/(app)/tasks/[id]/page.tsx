"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { RequireRole } from "@/components/app-shell";
import { FindingsView } from "@/components/findings-view";
import { useUser } from "@/components/session";
import { Alert, Button, Card, EmptyState, Field, Icon, inputClass, LinkButton, Spinner } from "@/components/ui";
import { PriorityBadge, TaskStatusBadge } from "@/components/workflow-badges";
import { api, ApiError, apiUpload, errorMessage } from "@/lib/api";
import { CONDITION_LABEL, formatDate, formatDateTime, todayIso } from "@/lib/format";
import { can } from "@/lib/permissions";
import type { ObservedCondition, Task } from "@/lib/types";

const MAX_BYTES = 8 * 1024 * 1024;
const MAX_PHOTOS = 6;

export default function TaskPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <RequireRole allowed={can.viewTasks}>
      <TaskView id={id} />
    </RequireRole>
  );
}

function TaskView({ id }: { id: string }) {
  const user = useUser();
  const [task, setTask] = useState<Task | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api<Task>(`/api/tasks/${id}`)
      .then(setTask)
      .catch((e) => (e instanceof ApiError && (e.status === 404 || e.status === 422) ? setNotFound(true) : setError(errorMessage(e))));
  }, [id]);
  useEffect(load, [load]);

  async function act(path: string, json: unknown = {}) {
    setBusy(true);
    setError(null);
    try {
      setTask(await api<Task>(`/api/tasks/${id}/${path}`, { method: "POST", json }));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  if (notFound) return <div className="p-8"><EmptyState icon="search" title="Task not found" action={<LinkButton href="/tasks" variant="secondary">Back to tasks</LinkButton>} /></div>;
  if (!task) return error ? <div className="p-8"><Alert>{error}</Alert></div> : <div className="flex justify-center py-24 text-muted"><Spinner className="h-6 w-6" /></div>;

  const mine = user.role === "inspector" && task.assignee_id === user.id;
  const open = task.status === "assigned" || task.status === "in_progress";

  return (
    <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6">
      <Link href="/tasks" className="mb-4 inline-flex min-h-9 items-center gap-1 text-sm font-medium text-primary-ink hover:underline">
        <Icon name="back" className="h-4 w-4" /> {user.role === "inspector" ? "My tasks" : "Tasks"}
      </Link>
      <div className="mb-5">
        <p className="text-cap font-medium text-muted first-letter:uppercase">{task.task_type} task</p>
        <h1 className="mt-0.5 text-2xl font-semibold tracking-tight text-ink sm:text-3xl" data-testid="task-title">{task.title}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-2" data-testid="task-status">
          <TaskStatusBadge status={task.status} overdue={task.overdue} />
          <PriorityBadge priority={task.priority} />
        </div>
      </div>
      {error && <div className="mb-4"><Alert>{error}</Alert></div>}

      <Card className="mb-4">
        <dl className="grid gap-x-6 gap-y-1 px-5 py-4 text-sm text-ink sm:grid-cols-label sm:gap-y-2.5">
          <dt className="text-muted">Green space</dt>
          <dd><Link href={`/sites/${task.site_id}`} className="font-medium text-primary-ink underline underline-offset-4">{task.site_name}</Link>
            {task.site_name_ar && task.site_name_ar !== task.site_name && <span className="ms-2 text-ink-2" lang="ar" dir="rtl">{task.site_name_ar}</span>}
            <span className="text-muted"> · <bdi>{task.district_name ?? "No district"}</bdi></span></dd>
          <dt className="mt-2 text-muted sm:mt-0">Due</dt>
          <dd>{formatDate(task.due_date)}</dd>
          <dt className="mt-2 text-muted sm:mt-0">Assigned to</dt>
          <dd>{task.assignee_name}{task.created_by_name ? ` · by ${task.created_by_name}` : ""} · {formatDateTime(task.created_at)}</dd>
          {task.signal_id && (<><dt className="mt-2 text-muted sm:mt-0">Signal</dt><dd>{can.viewSignals(user.role)
            ? <Link href={`/signals/${task.signal_id}`} className="text-primary-ink underline underline-offset-4">View the satellite evidence</Link>
            : "Raised from a satellite signal"}</dd></>)}
          {task.instructions && (<><dt className="mt-2 text-muted sm:mt-0">Instructions</dt><dd className="whitespace-pre-line">{task.instructions}</dd></>)}
        </dl>
      </Card>

      {mine && open ? (
        <InspectorWork task={task} busy={busy} onTask={setTask} onAct={act} />
      ) : (
        <Card title="Field findings" className="mb-4">
          <div className="px-5 py-4">
            {task.finding ? <FindingsView finding={task.finding} /> : <p className="text-sm text-muted">No findings recorded yet.</p>}
          </div>
        </Card>
      )}

      {can.manageTasks(user.role) && open && (
        <Card title="Manage" className="mb-4">
          <div className="flex flex-wrap gap-2 px-5 py-4">
            <Button variant="danger" busy={busy} onClick={() => act("cancel", { reason: null })}>Cancel task</Button>
            <p className="basis-full text-cap text-muted">Cancelling the only inspection task of a signal returns the signal to the attention queue.</p>
          </div>
        </Card>
      )}
    </div>
  );
}

function InspectorWork({ task, busy, onTask, onAct }: {
  task: Task; busy: boolean; onTask: (t: Task) => void; onAct: (path: string) => Promise<void>;
}) {
  const f = task.finding;
  const [visit, setVisit] = useState(f?.visit_date ?? todayIso());
  const [condition, setCondition] = useState<ObservedCondition | "">(f?.condition ?? "");
  const [notes, setNotes] = useState(f?.notes ?? "");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function save(e?: FormEvent): Promise<boolean> {
    e?.preventDefault();
    setSaving(true);
    setErrors({});
    setSaved(false);
    try {
      onTask(await api<Task>(`/api/tasks/${task.id}/findings`, {
        method: "PUT",
        json: { visit_date: visit || null, condition: condition || null, notes: notes || null },
      }));
      setSaved(true);
      return true;
    } catch (err) {
      setErrors(err instanceof ApiError && Object.keys(err.fieldErrors).length ? err.fieldErrors : { form: errorMessage(err) });
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function complete() {
    const local: Record<string, string> = {};
    if (!visit) local.visit_date = "Enter the visit date.";
    if (!condition) local.condition = "Choose the observed condition.";
    if (!notes.trim()) local.notes = "Describe what you found.";
    if (Object.keys(local).length) return setErrors(local);
    if (await save()) await onAct("complete");
  }

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setErrors({});
    const count = (task.finding?.photos.length ?? 0);
    const list = Array.from(files).slice(0, Math.max(0, MAX_PHOTOS - count));
    if (files.length + count > MAX_PHOTOS) setErrors({ file: `A finding can have at most ${MAX_PHOTOS} photos.` });
    setUploading(true);
    try {
      for (const file of list) {
        if (file.size > MAX_BYTES) {
          setErrors({ file: `${file.name} is larger than 8 MB.` });
          continue;
        }
        const form = new FormData();
        form.append("file", file);
        onTask(await apiUpload<Task>(`/api/tasks/${task.id}/photos`, form));
      }
    } catch (err) {
      setErrors({ file: err instanceof ApiError ? Object.values(err.fieldErrors)[0] ?? err.message : errorMessage(err) });
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function removePhoto(photoId: string) {
    try {
      onTask(await api<Task>(`/api/tasks/${task.id}/photos/${photoId}`, { method: "DELETE" }));
    } catch (err) {
      setErrors({ file: errorMessage(err) });
    }
  }

  return (
    <>
      {task.status === "assigned" && (
        <div className="mb-4">
          <Button busy={busy} onClick={() => onAct("start")} className="w-full sm:w-auto">Start task</Button>
        </div>
      )}
      <Card title="Field findings" className="mb-4">
        <form onSubmit={save} noValidate className="space-y-4 px-5 py-4" data-testid="findings-form">
          {errors.form && <Alert>{errors.form}</Alert>}
          <Field label="Visit date" htmlFor="visit-date" error={errors.visit_date}>
            <input id="visit-date" type="date" max={todayIso()} value={visit} onChange={(e) => setVisit(e.target.value)}
              className={inputClass(!!errors.visit_date)} aria-invalid={!!errors.visit_date || undefined} />
          </Field>
          <fieldset>
            <legend className="mb-1.5 text-sm font-medium text-ink">Observed condition</legend>
            <div className="grid gap-2">
              {(Object.keys(CONDITION_LABEL) as ObservedCondition[]).map((c) => (
                <label key={c} className="flex min-h-11 items-center gap-3 rounded-md px-3 py-2 text-base text-ink ring-1 ring-inset ring-line transition-colors duration-fast has-checked:bg-primary-soft has-checked:ring-2 has-checked:ring-primary">
                  <input type="radio" name="condition" value={c} checked={condition === c} onChange={() => setCondition(c)} className="h-4 w-4 accent-primary" />
                  {CONDITION_LABEL[c]}
                </label>
              ))}
            </div>
            {errors.condition && <p role="alert" className="mt-1 text-cap font-medium text-danger-ink">{errors.condition}</p>}
          </fieldset>
          <Field label="Notes" htmlFor="finding-notes" error={errors.notes}>
            <textarea id="finding-notes" rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={4000}
              className={inputClass(!!errors.notes)} aria-invalid={!!errors.notes || undefined} />
          </Field>
          <Button type="submit" variant="secondary" busy={saving}>Save draft</Button>
          {saved && <span role="status" className="ms-3 text-sm text-primary-ink">Saved</span>}
        </form>
      </Card>

      <Card title={`Photos (${task.finding?.photos.length ?? 0} of ${MAX_PHOTOS})`} className="mb-4">
        <div className="space-y-3 px-5 py-4">
          {task.finding && task.finding.photos.length > 0 && (
            <ul className="flex flex-wrap gap-2" data-testid="photo-list">
              {task.finding.photos.map((p, i) => (
                <li key={p.id} className="relative">
                  {/* eslint-disable-next-line @next/next/no-img-element -- authenticated API image */}
                  <img src={p.thumb_url} alt={`Photo ${i + 1}`} className="h-24 w-32 rounded-md object-cover ring-1 ring-line" />
                  <button type="button" onClick={() => removePhoto(p.id)} aria-label={`Remove photo ${i + 1}`}
                    className="absolute right-1 top-1 grid h-8 w-8 place-items-center rounded-full bg-surface/90 text-danger-ink shadow-sm"><Icon name="close" className="h-4 w-4" /></button>
                </li>
              ))}
            </ul>
          )}
          <label className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-md border border-dashed border-line-strong px-4 py-2 text-sm font-medium text-primary-ink hover:bg-primary-soft">
            <Icon name="camera" className="h-4 w-4" /> {uploading ? "Uploading…" : "Add photos"}
            <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" multiple capture="environment" className="sr-only"
              onChange={(e) => upload(e.target.files)} disabled={uploading} data-testid="photo-input" />
          </label>
          <p className="text-cap text-muted">JPEG, PNG or WebP, up to 8 MB each. Location and camera data are removed when saved.</p>
          {errors.file && <Alert>{errors.file}</Alert>}
        </div>
      </Card>

      <div className="sticky bottom-0 -mx-4 border-t border-line bg-surface px-4 py-3 sm:static sm:mx-0 sm:border-0 sm:bg-transparent sm:p-0">
        <Button busy={busy || saving} onClick={complete} className="w-full sm:w-auto">Complete task</Button>
      </div>
    </>
  );
}
