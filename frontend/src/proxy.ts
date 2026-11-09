import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Optimistic sign-in check: pages are only served to requests carrying a session cookie.
 * The backend validates the session on every API call; this only avoids rendering
 * protected screens for visitors who have clearly not signed in.
 */
export function proxy(request: NextRequest) {
  if (request.cookies.has("namaa_session")) return NextResponse.next();
  // Visitors without a session see the public introduction at "/" instead of being sent to sign in.
  if (request.nextUrl.pathname === "/") return NextResponse.rewrite(new URL("/welcome", request.url));
  const url = new URL("/login", request.url);
  const next = request.nextUrl.pathname + request.nextUrl.search;
  if (next !== "/") url.searchParams.set("next", next);
  return NextResponse.redirect(url);
}

export const config = {
  // Static files (including the MapLibre worker under /vendor) never need a session.
  matcher: ["/((?!api|login|reset-password|welcome|vendor|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|ico|mjs)$).*)"],
};
