import { OUTCOME_LABEL, PRIORITY_LABEL, SIGNAL_STATUS_LABEL, TASK_STATUS_LABEL } from "@/lib/format";
import type { SignalOutcome, SignalStatus, TaskPriority, TaskStatus } from "@/lib/types";
import { Badge, Icon } from "./ui";

/* Status is always colour + icon + word, never colour alone. */

export function SignalStatusBadge({ status, outcome }: { status: SignalStatus; outcome?: SignalOutcome | null }) {
  if (status === "closed")
    return (
      <Badge tone={outcome === "not_confirmed" ? "neutral" : "primary"}>
        <Icon name="check" className="h-3.5 w-3.5" /> Closed{outcome ? ` · ${OUTCOME_LABEL[outcome]}` : ""}
      </Badge>
    );
  const map = {
    open: { tone: "signal", icon: "alert" },
    under_inspection: { tone: "info", icon: "clipboard" },
    dismissed: { tone: "neutral", icon: "close" },
  } as const;
  const m = map[status];
  return (
    <Badge tone={m.tone}>
      <Icon name={m.icon} className="h-3.5 w-3.5" /> {SIGNAL_STATUS_LABEL[status]}
    </Badge>
  );
}

export function TaskStatusBadge({ status, overdue }: { status: TaskStatus; overdue?: boolean }) {
  const map = {
    assigned: { tone: "neutral", icon: "clipboard" },
    in_progress: { tone: "info", icon: "clock" },
    completed: { tone: "primary", icon: "check" },
    cancelled: { tone: "neutral", icon: "close" },
  } as const;
  const m = map[status];
  return (
    <span className="inline-flex flex-wrap gap-1">
      <Badge tone={m.tone}>
        <Icon name={m.icon} className="h-3.5 w-3.5" /> {TASK_STATUS_LABEL[status]}
      </Badge>
      {overdue && (
        <Badge tone="danger">
          <Icon name="alert" className="h-3.5 w-3.5" /> Overdue
        </Badge>
      )}
    </span>
  );
}

export function PriorityBadge({ priority }: { priority: TaskPriority }) {
  const tone = priority === "high" ? "signal" : priority === "medium" ? "warn" : "neutral";
  return <Badge tone={tone}>{PRIORITY_LABEL[priority]} priority</Badge>;
}
