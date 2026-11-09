"use client";

import Link from "next/link";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { cx, Icon, type IconName } from "./ui";

/* Short confirmations ("Saved", "Link copied", "Run finished") that do not need a page or a dialog. */

type Tone = "success" | "info" | "danger";
type Toast = { id: number; tone: Tone; text: string; href?: string; action?: string };
type Push = (t: Omit<Toast, "id">) => void;

const ToastContext = createContext<Push>(() => undefined);
export const useToast = () => useContext(ToastContext);

const ICON: Record<Tone, IconName> = { success: "check", info: "info", danger: "alert" };
const TONE: Record<Tone, string> = { success: "text-primary-ink", info: "text-info-ink", danger: "text-danger-ink" };

let next = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const dismiss = useCallback((id: number) => setToasts((all) => all.filter((t) => t.id !== id)), []);
  const push = useCallback<Push>(
    (t) => {
      const id = next++;
      setToasts((all) => [...all.slice(-2), { ...t, id }]);
      setTimeout(() => dismiss(id), t.tone === "danger" ? 8000 : 5000);
    },
    [dismiss],
  );
  const value = useMemo(() => push, [push]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div aria-live="polite" role="status" className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 px-4">
        {toasts.map((t) => (
          <div key={t.id} data-testid="toast"
            className="pointer-events-auto flex max-w-md animate-fade-up items-center gap-3 rounded-md bg-surface px-4 py-3 text-sm text-ink shadow-lg ring-1 ring-line">
            <Icon name={ICON[t.tone]} className={cx("h-4 w-4 shrink-0", TONE[t.tone])} />
            <span className="min-w-0">{t.text}</span>
            {t.href && (
              <Link href={t.href} onClick={() => dismiss(t.id)} className="shrink-0 font-medium text-primary-ink underline underline-offset-4">
                {t.action ?? "Open"}
              </Link>
            )}
            <button type="button" onClick={() => dismiss(t.id)} className="-mr-1 grid h-8 w-8 shrink-0 place-items-center rounded-sm text-muted hover:text-ink">
              <span className="sr-only">Dismiss</span>
              <Icon name="close" className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
