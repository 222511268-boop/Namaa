import type { RunStatus } from "@/lib/types";
import { Badge, Icon, Spinner } from "./ui";

/** Status always pairs colour with an icon and a word (never colour alone). */
export function RunStatusBadge({ status }: { status: RunStatus }) {
  switch (status) {
    case "queued":
      return <Badge tone="neutral"><Icon name="refresh" className="h-3.5 w-3.5" /> Queued</Badge>;
    case "running":
      return <Badge tone="info"><Spinner className="h-3 w-3" /> Running</Badge>;
    case "succeeded":
      return <Badge tone="primary"><Icon name="check" className="h-3.5 w-3.5" /> Completed</Badge>;
    case "failed":
      return <Badge tone="danger"><Icon name="alert" className="h-3.5 w-3.5" /> Failed</Badge>;
  }
}
