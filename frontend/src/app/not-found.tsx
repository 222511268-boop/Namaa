"use client";

import Link from "next/link";
import { buttonClass } from "@/components/ui";

export default function NotFound() {
  return (
    <div className="grid min-h-screen place-items-center px-6 text-center">
      <div>
        <p className="num text-sm font-medium text-primary-ink">404</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight text-ink">Page not found</h1>
        <p className="mt-2 text-base text-muted">The page you are looking for does not exist.</p>
        <Link href="/" className={buttonClass("primary", "md", "mt-6")}>Go to overview</Link>
      </div>
    </div>
  );
}
