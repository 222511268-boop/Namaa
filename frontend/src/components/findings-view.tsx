import { CONDITION_LABEL, formatDate } from "@/lib/format";
import type { Finding } from "@/lib/types";

/** Read-only display of field findings and photographs. */
export function FindingsView({ finding }: { finding: Finding }) {
  return (
    <div className="space-y-2 text-sm" data-testid="findings-view">
      <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-label">
        <dt className="text-muted">Visited</dt>
        <dd>{formatDate(finding.visit_date)}</dd>
        <dt className="text-muted">Observed condition</dt>
        <dd className="font-medium text-ink">{finding.condition ? CONDITION_LABEL[finding.condition] : "—"}</dd>
        <dt className="text-muted">Notes</dt>
        <dd className="whitespace-pre-line">{finding.notes ?? "—"}</dd>
      </dl>
      {finding.photos.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label="Field photographs">
          {finding.photos.map((p, i) => (
            <li key={p.id}>
              <a href={p.url} target="_blank" rel="noopener noreferrer" className="block overflow-hidden rounded-md ring-1 ring-line">
                {/* eslint-disable-next-line @next/next/no-img-element -- authenticated API image, not optimisable */}
                <img src={p.thumb_url} alt={`Field photograph ${i + 1}`} className="h-24 w-32 object-cover" loading="lazy" />
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
