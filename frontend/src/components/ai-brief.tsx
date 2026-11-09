"use client";

import { useEffect, useState, type ReactNode } from "react";
import { api, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { AiBrief, AiStatus, Evidence, Fact, SignalBriefContent } from "@/lib/types";
import { Alert, Badge, Button, Card, Icon, Skeleton, cx } from "./ui";

/** "AI-generated, advisory" marker shown on every piece of AI output (US26, US27, NFR07). */
export function AiLabel({ text }: { text: string }) {
  return (
    <p className="flex items-start gap-2 rounded-md bg-info-soft px-3 py-2 text-cap text-info-ink" data-testid="ai-label">
      <Icon name="sparkle" className="mt-px h-4 w-4 shrink-0" />
      <span>{text}</span>
    </p>
  );
}

function factText(f: Fact) {
  return `${f.label}: ${f.value}${f.unit ? ` ${f.unit}` : ""}`;
}

/** Text with links to the stored facts it relies on. */
export function Cited({ ev, facts, prefix }: { ev: Evidence; facts: Map<string, Fact>; prefix: string }) {
  return (
    <>
      {ev.text}
      {ev.fact_ids.map((id) => {
        const f = facts.get(id);
        return (
          <a key={id} href={`#${prefix}-${id}`} title={f ? factText(f) : id}
            className="num ml-1 rounded-sm bg-surface-2 px-1 align-baseline text-cap text-ink-2 ring-1 ring-line hover:text-ink">
            {id}
          </a>
        );
      })}
    </>
  );
}

/** Every fact sent to the AI service, so each figure can be checked against its stored value. */
export function FactList({ facts, prefix }: { facts: Fact[]; prefix: string }) {
  return (
    <details className="group rounded-md ring-1 ring-line print:hidden">
      <summary className="flex min-h-10 cursor-pointer items-center gap-2 px-3 text-sm font-medium text-ink-2 hover:text-ink">
        <Icon name="list" className="h-4 w-4" /> Stored facts used ({facts.length})
      </summary>
      <dl className="grid max-h-72 grid-cols-[auto_1fr_auto] gap-x-3 gap-y-1 overflow-y-auto border-t border-line px-3 py-2 text-cap">
        {facts.map((f) => (
          <div key={f.id} id={`${prefix}-${f.id}`} className="contents target:[&>*]:bg-primary-soft">
            <dt className="num text-muted">{f.id}</dt>
            <dd className="text-ink-2">{f.label}</dd>
            <dd className="num text-right font-medium text-ink">{String(f.value)}{f.unit ? ` ${f.unit}` : ""}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

export function useAiStatus() {
  const [status, setStatus] = useState<AiStatus | null>(null);
  useEffect(() => {
    api<AiStatus>("/api/ai/status").then(setStatus).catch(() => setStatus(null));
  }, []);
  return status;
}

const ASSESSMENT_TONE = { "more likely": "signal", possible: "neutral", "less likely": "neutral" } as const;

function Explanations({ content, facts }: { content: SignalBriefContent; facts: Map<string, Fact> }) {
  return (
    <ol className="space-y-3">
      {content.explanations.map((e, i) => (
        <li key={i} className="rounded-md p-3 ring-1 ring-line">
          <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-ink">
            {e.title} <Badge tone={ASSESSMENT_TONE[e.assessment]}>{e.assessment}</Badge>
          </p>
          <div className="mt-2 grid gap-3 text-sm sm:grid-cols-2">
            <EvidenceList title="Supporting evidence" items={e.supporting} facts={facts} icon="check" />
            <EvidenceList title="Contradicting evidence" items={e.contradicting} facts={facts} icon="close" />
          </div>
        </li>
      ))}
    </ol>
  );
}

function EvidenceList({ title, items, facts, icon }: { title: string; items: Evidence[]; facts: Map<string, Fact>; icon: "check" | "close" }) {
  return (
    <div>
      <p className="text-cap font-medium text-muted">{title}</p>
      <ul className="mt-1 space-y-1">
        {items.map((ev, i) => (
          <li key={i} className="flex gap-1.5 text-ink-2">
            <Icon name={icon} className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted" />
            <span><Cited ev={ev} facts={facts} prefix="brief" /></span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * AI evidence brief for a signal (US26). Generated only on request; failures leave the rest of the page usable.
 * `onChecklist` receives the drafted checklist so the inspection form can be pre-filled.
 */
export function SignalBriefCard({ signalId, canGenerate, onChecklist, footer }: {
  signalId: string; canGenerate: boolean; onChecklist?: (text: string) => void; footer?: ReactNode;
}) {
  const status = useAiStatus();
  const [brief, setBrief] = useState<AiBrief<SignalBriefContent> | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<AiBrief<SignalBriefContent> | null>(`/api/signals/${signalId}/brief`).then(setBrief).catch(() => setBrief(null));
  }, [signalId]);
  useEffect(() => {
    onChecklist?.(brief && !brief.outdated ? brief.checklist_text ?? "" : "");
  }, [brief, onChecklist]);

  async function generate(force = false) {
    setBusy(true);
    setError(null);
    try {
      setBrief(await api<AiBrief<SignalBriefContent>>(`/api/signals/${signalId}/brief`, { method: "POST", json: { force } }));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const facts = new Map((brief?.facts ?? []).map((f) => [f.id, f]));
  const disabled = status !== null && !status.enabled;
  return (
    <Card id="ai-brief" title={<span className="inline-flex items-center gap-2"><Icon name="sparkle" className="h-4 w-4 text-primary-ink" /> AI evidence brief</span>}
      action={brief && canGenerate ? (
        <Button size="sm" variant="ghost" busy={busy} disabled={disabled} onClick={() => void generate(true)}>
          <Icon name="refresh" className="h-4 w-4" /> {brief.outdated ? "Update brief" : "Regenerate"}
        </Button>
      ) : undefined}>
      <div className="space-y-3 p-5 pt-3" aria-live="polite" aria-busy={busy}>
        {brief === undefined && <Skeleton className="h-16" />}
        {brief === null && !busy && (
          <div className="space-y-3">
            <p className="text-sm text-muted">
              A short, advisory summary of this signal&apos;s stored evidence with possible explanations and a drafted
              inspection checklist. Only selected facts are sent; no names, notes or photos.
            </p>
            {canGenerate ? (
              <Button variant="secondary" onClick={() => void generate()} disabled={disabled} data-testid="generate-brief">
                <Icon name="sparkle" className="h-4 w-4" /> Generate brief
              </Button>
            ) : (
              <p className="text-cap text-muted">Green-space managers can generate a brief.</p>
            )}
            {disabled && <p className="text-cap text-muted">AI assistance is not configured on this server.</p>}
          </div>
        )}
        {busy && !brief && <div className="space-y-2" aria-hidden="true"><Skeleton className="h-5 w-2/3" /><Skeleton className="h-16" /><Skeleton className="h-24" /></div>}
        {error && <Alert tone="warn">{error}</Alert>}
        {brief && (
          <div className={cx("space-y-4", busy && "opacity-60")} data-testid="brief">
            <AiLabel text={brief.label} />
            {brief.outdated && <Alert tone="info">The evidence has changed since this brief was generated.</Alert>}
            <div>
              <p className="font-medium text-ink">{brief.content.headline}</p>
              <p className="mt-1 text-sm text-ink-2"><Cited ev={brief.content.summary} facts={facts} prefix="brief" /></p>
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold text-ink">Possible explanations</h3>
              <Explanations content={brief.content} facts={facts} />
            </div>
            <div>
              <h3 className="mb-1 text-sm font-semibold text-ink">Drafted inspection checklist</h3>
              <ul className="list-disc space-y-0.5 pl-5 text-sm text-ink-2" data-testid="brief-checklist">
                {brief.content.checklist.map((c, i) => <li key={i}><Cited ev={c} facts={facts} prefix="brief" /></li>)}
              </ul>
              {footer}
            </div>
            {brief.content.data_gaps.length > 0 && (
              <div>
                <h3 className="mb-1 text-sm font-semibold text-ink">Data gaps</h3>
                <ul className="list-disc space-y-0.5 pl-5 text-sm text-muted">
                  {brief.content.data_gaps.map((g, i) => <li key={i}>{g}</li>)}
                </ul>
              </div>
            )}
            <FactList facts={brief.facts} prefix="brief" />
            <p className="text-cap text-muted">
              {brief.model} · prompt {brief.prompt_version} · {formatDateTime(brief.created_at)}
            </p>
          </div>
        )}
      </div>
    </Card>
  );
}
