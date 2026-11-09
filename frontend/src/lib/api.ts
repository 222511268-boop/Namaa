/** Thin client for the Namaa API (same origin, proxied to FastAPI). */

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public fieldErrors: Record<string, string> = {},
  ) {
    super(message);
  }
}

type Detail = string | { loc?: (string | number)[]; msg: string }[] | undefined;

function parseDetail(detail: Detail, status: number): { message: string; fields: Record<string, string> } {
  if (typeof detail === "string") return { message: detail, fields: {} };
  if (!Array.isArray(detail) || detail.length === 0)
    return {
      message:
        status >= 500
          ? `The server could not complete the request (HTTP ${status}). Please try again; if it persists, contact your administrator.`
          : `The request was not accepted (HTTP ${status}).`,
      fields: {},
    };
  const fields: Record<string, string> = {};
  if (Array.isArray(detail)) {
    for (const err of detail) {
      const field = String(err.loc?.[err.loc.length - 1] ?? "form");
      // Pydantic prefixes custom messages with "Value error, ".
      fields[field] ??= err.msg.replace(/^Value error, /, "");
    }
  }
  return { message: "Please correct the highlighted fields.", fields };
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  let res: Response;
  try {
    res = await fetch(path, {
      ...rest,
      headers: { ...(json !== undefined ? { "Content-Type": "application/json" } : {}), ...headers },
      body: json !== undefined ? JSON.stringify(json) : rest.body,
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "The server could not be reached. Check your connection and try again.");
  }
  if (res.status === 401 && !path.startsWith("/api/auth/login")) {
    const next = window.location.pathname + window.location.search;
    // Called outside React (no router available); a full reload also clears stale client state.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign(`/login?expired=1&next=${encodeURIComponent(next)}`);
    throw new ApiError(401, "Your session has ended.");
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const { message, fields } = parseDetail(body.detail, res.status);
    throw new ApiError(res.status, message || `Request failed (${res.status}).`, fields);
  }
  return body as T;
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const first = Object.values(err.fieldErrors)[0];
    return Object.keys(err.fieldErrors).length === 1 && first ? first : err.message;
  }
  return "Something went wrong. Please try again.";
}

/** Multipart upload (photos). Same error handling as api(). */
export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  return api<T>(path, { method: "POST", body: form });
}
