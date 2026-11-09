"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { RequireRole } from "@/components/app-shell";
import { useUser } from "@/components/session";
import { Alert, Card, cx, EmptyState, Icon, inputClass, LinkButton, PageHeader, Spinner } from "@/components/ui";
import { PriorityBadge, TaskStatusBadge } from "@/components/workflow-badges";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { can } from "@/lib/permissions";
import type { Task } from "@/lib/types";

const FILTERS = [
  ["open", "Open (assigned or in progress)"],
  ["completed", "Completed"],
  ["cancelled", "Cancelled"],
  ["all", "All"],
] as const;

export default function TasksPage() {
  const user = useUser();
  const inspector = user.role === "inspector";
  const [status, setStatus] = useState("open");
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [loaded, setLoaded] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stale = false;
    api<Task[]>(`/api/tasks?status=${status}`)
      .then((t) => !stale && (setTasks(t), setError(null)))
      .catch((e) => !stale && setError(errorMessage(e)))
      .finally(() => !stale && setLoaded(status));
    return () => {
      stale = true;
    };
  }, [status]);

  return (
    <RequireRole allowed={can.viewTasks}>
      <div className="mx-auto max-w-content px-4 py-6 sm:px-6 sm:py-8">
        <PageHeader
          title={inspector ? "My tasks" : "Tasks"}
          subtitle={inspector ? "Field visits assigned to you." : "Inspection and maintenance work across all green spaces."}
          actions={can.manageTasks(user.role) ? <LinkButton href="/tasks/new"><Icon name="plus" className="h-4 w-4" />New task</LinkButton> : undefined}
        />
        <div className="mb-4">
          <label htmlFor="task-status" className="mb-1 block text-cap font-medium text-muted">Show</label>
          <select id="task-status" value={status} onChange={(e) => setStatus(e.target.value)} className={cx(inputClass(), "max-w-xs")}>
            {FILTERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        {error && <Alert>{error}</Alert>}
        {!tasks && !error && <div className="flex justify-center py-16 text-muted"><Spinner className="h-6 w-6" /></div>}
        {tasks && tasks.length === 0 && (
          <Card>
            <EmptyState icon="clipboard" title={status === "open" ? "No open tasks" : "No tasks to show"}>
              {inspector ? "Tasks assigned to you will appear here." : "Create a task from a site profile or a signal."}
            </EmptyState>
          </Card>
        )}
        {tasks && tasks.length > 0 && (
          <ul className={cx("space-y-3", loaded !== status && "opacity-60")} data-testid="task-list">
            {tasks.map((t) => (
              <li key={t.id}>
                <Link href={`/tasks/${t.id}`} className="block rounded-lg bg-surface p-4 shadow-xs ring-1 ring-line transition-shadow duration-base hover:shadow-md">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-medium text-ink">{t.title}</p>
                      <p className="text-sm text-ink-2">{t.site_name} · <bdi>{t.district_name ?? "No district"}</bdi></p>
                    </div>
                    <TaskStatusBadge status={t.status} overdue={t.overdue} />
                  </div>
                  <p className="mt-2 flex flex-wrap items-center gap-2 text-cap text-muted">
                    <span className="capitalize">{t.task_type}</span>
                    <PriorityBadge priority={t.priority} />
                    <span>Due {formatDate(t.due_date)}</span>
                    {!inspector && <span>· {t.assignee_name}</span>}
                    {t.signal_id && <span>· linked to a signal</span>}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </RequireRole>
  );
}
