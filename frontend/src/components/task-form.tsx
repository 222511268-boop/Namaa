"use client";

import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError, errorMessage } from "@/lib/api";
import { PRIORITY_LABEL, todayIso } from "@/lib/format";
import type { Inspector, TaskPriority } from "@/lib/types";
import { Alert, Button, Field, inputClass } from "./ui";

type TaskFormValues = {
  title: string;
  instructions: string;
  priority: TaskPriority;
  due_date: string;
  assignee_id: string;
};

/** Shared task fields; the caller decides where the values are sent. */
export function TaskForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
  extra,
  suggestedInstructions,
}: {
  initial?: Partial<TaskFormValues>;
  submitLabel: string;
  onSubmit: (v: TaskFormValues) => Promise<void>;
  onCancel?: () => void;
  extra?: React.ReactNode;
  suggestedInstructions?: string;
}) {
  const [inspectors, setInspectors] = useState<Inspector[] | null>(null);
  const [v, setV] = useState<TaskFormValues>({
    title: initial?.title ?? "",
    instructions: initial?.instructions ?? "",
    priority: initial?.priority ?? "medium",
    due_date: initial?.due_date ?? todayIso(3),
    assignee_id: initial?.assignee_id ?? "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Inspector[]>("/api/inspectors").then(setInspectors).catch((e) => setErrors({ form: errorMessage(e) }));
  }, []);

  const set = (k: keyof TaskFormValues) => (e: { target: { value: string } }) => setV({ ...v, [k]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    const local: Record<string, string> = {};
    if (v.title.trim().length < 3) local.title = "Give the task a title of at least 3 characters.";
    if (!v.assignee_id) local.assignee_id = "Choose a field inspector.";
    if (!v.due_date) local.due_date = "Choose a due date.";
    setErrors(local);
    if (Object.keys(local).length) return;
    setBusy(true);
    try {
      await onSubmit(v);
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fieldErrors).length) setErrors(err.fieldErrors);
      else setErrors({ form: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="@container space-y-4">
      {errors.form && <Alert>{errors.form}</Alert>}
      {extra}
      {suggestedInstructions && suggestedInstructions !== v.instructions && <Button type="button" size="sm" variant="secondary" onClick={() => setV({ ...v, instructions: suggestedInstructions })}>Use latest AI checklist</Button>}
      <Field label="Task title" htmlFor="task-title" error={errors.title}>
        <input id="task-title" value={v.title} onChange={set("title")} maxLength={160} className={inputClass(!!errors.title)} />
      </Field>
      {/* Responds to the form's own width: one column in the narrow decision panel, three on a full page. */}
      <div className="grid gap-4 @lg:grid-cols-3">
        <Field label="Assign to" htmlFor="task-assignee" error={errors.assignee_id}>
          <select id="task-assignee" value={v.assignee_id} onChange={set("assignee_id")} className={inputClass(!!errors.assignee_id)}>
            <option value="">{inspectors === null ? "Loading…" : inspectors.length ? "Choose inspector…" : "No active inspectors"}</option>
            {inspectors?.map((i) => <option key={i.id} value={i.id}>{i.full_name}</option>)}
          </select>
        </Field>
        <Field label="Due date" htmlFor="task-due" error={errors.due_date}>
          <input id="task-due" type="date" min={todayIso()} value={v.due_date} onChange={set("due_date")} className={inputClass(!!errors.due_date)} />
        </Field>
        <Field label="Priority" htmlFor="task-priority" error={errors.priority}>
          <select id="task-priority" value={v.priority} onChange={set("priority")} className={inputClass()}>
            {(Object.keys(PRIORITY_LABEL) as TaskPriority[]).map((p) => <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}
          </select>
        </Field>
      </div>
      <Field label="Instructions (optional)" htmlFor="task-instructions" error={errors.instructions}>
        <textarea id="task-instructions" rows={3} value={v.instructions} onChange={set("instructions")} maxLength={4000} className={inputClass()} />
      </Field>
      <div className="flex gap-2">
        <Button type="submit" busy={busy}>{submitLabel}</Button>
        {onCancel && <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>}
      </div>
    </form>
  );
}
