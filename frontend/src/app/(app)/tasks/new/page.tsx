"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { RequireRole } from "@/components/app-shell";
import { TaskForm } from "@/components/task-form";
import { Card, Field, inputClass, PageHeader, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { can } from "@/lib/permissions";
import type { SiteSummary, Task, TaskType } from "@/lib/types";

function NewTask() {
  const router = useRouter();
  const params = useSearchParams();
  const [sites, setSites] = useState<SiteSummary[] | null>(null);
  const [siteId, setSiteId] = useState(params.get("site") ?? "");
  const [taskType, setTaskType] = useState<TaskType>("maintenance");
  const [siteError, setSiteError] = useState<string | undefined>();

  useEffect(() => {
    api<SiteSummary[]>("/api/sites").then(setSites).catch(() => setSites([]));
  }, []);

  if (!sites) return <div className="flex justify-center py-16 text-muted"><Spinner className="h-6 w-6" /></div>;
  const site = sites.find((s) => s.id === siteId);
  return (
    <Card>
      <div className="p-5">
        <TaskForm
          submitLabel="Create task"
          initial={{ title: site ? `Maintenance at ${site.name}`.slice(0, 160) : "" }}
          extra={
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Green space" htmlFor="task-site" error={siteError}>
                <select id="task-site" value={siteId} onChange={(e) => setSiteId(e.target.value)} className={inputClass(!!siteError)}>
                  <option value="">Choose a site…</option>
                  {sites.map((s) => <option key={s.id} value={s.id}>{s.name}{s.district_name ? ` · ${s.district_name}` : ""}</option>)}
                </select>
              </Field>
              <Field label="Task type" htmlFor="task-type">
                <select id="task-type" value={taskType} onChange={(e) => setTaskType(e.target.value as TaskType)} className={inputClass()}>
                  <option value="maintenance">Maintenance</option>
                  <option value="inspection">Inspection</option>
                </select>
              </Field>
            </div>
          }
          onCancel={() => router.back()}
          onSubmit={async (v) => {
            if (!siteId) {
              setSiteError("Choose a green space.");
              return;
            }
            setSiteError(undefined);
            const t = await api<Task>("/api/tasks", { method: "POST", json: { ...v, site_id: siteId, task_type: taskType } });
            router.push(`/tasks/${t.id}`);
          }}
        />
      </div>
    </Card>
  );
}

export default function NewTaskPage() {
  return (
    <RequireRole allowed={can.manageTasks}>
      <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
        <PageHeader title="New task" subtitle="Assign inspection or maintenance work to a field inspector." />
        <Suspense>
          <NewTask />
        </Suspense>
      </div>
    </RequireRole>
  );
}
