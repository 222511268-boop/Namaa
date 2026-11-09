"use client";

import { useEffect, useRef, type ReactNode } from "react";

/**
 * Fades its children up once they scroll into view. The hidden starting state only applies when the
 * visitor has not asked for reduced motion (see globals.css), so content is never held back for them.
 */
export function Reveal({ children, className, delay = 0, as: Tag = "div" }: {
  children?: ReactNode;
  className?: string;
  delay?: number;
  as?: "div" | "li" | "section";
}) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          el.dataset.shown = "";
          io.disconnect();
        }
      },
      { rootMargin: "0px 0px -10% 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return (
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    <Tag ref={ref as any} data-reveal="" className={className} style={delay ? { transitionDelay: `${delay}ms` } : undefined}>
      {children}
    </Tag>
  );
}
