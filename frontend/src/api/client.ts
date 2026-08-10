/**
 * The single API client.
 *
 * DEM-003 — what was removed and why
 * -----------------------------------
 * There were two. `api/client.ts` used fetch against `http://localhost:8001`
 * reading the token from `finsage_auth`; `services/api.ts` used axios against
 * `http://localhost:8000/api/v1` reading it from a key called `token`.
 * Different ports, different storage keys, different transports. One of them
 * was dead code and it was not obvious which.
 *
 * This is now the only client. Requests are RELATIVE, so the Vite dev proxy
 * handles them and CORS is unnecessary — both clients previously hardcoded an
 * absolute origin, which defeated the proxy the README described.
 */

const TOKEN_STORE = 'finsage_auth';

/** Base path. Empty by default so requests stay relative and use the proxy. */
const BASE = import.meta.env.VITE_API_BASE_URL ?? '';

export class ApiError extends Error {
  status: number;
  /** Server correlation id, for matching a user report to a log line. */
  correlationId?: string;

  constructor(message: string, status: number, correlationId?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.correlationId = correlationId;
  }
}

function readToken(): string | null {
  try {
    const raw = localStorage.getItem(TOKEN_STORE);
    return raw ? (JSON.parse(raw)?.state?.token ?? null) : null;
  } catch {
    return null;
  }
}

/** Broadcast so the app can route to login without this module importing the store. */
function onUnauthorized() {
  window.dispatchEvent(new Event('auth-unauthorized'));
}

async function request<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const token = readToken();

  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {}),
    },
  });

  if (res.status === 401) {
    onUnauthorized();
    throw new ApiError('Your session has expired. Please sign in again.', 401);
  }

  if (!res.ok) {
    let detail = res.statusText;
    let correlationId: string | undefined;
    try {
      const body = await res.json();
      detail = body.detail ?? body.message ?? detail;
      correlationId = body.correlation_id;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, res.status, correlationId);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  get: <T = any>(path: string) => request<T>(path, { method: 'GET' }),
  post: <T = any>(path: string, data?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: data !== undefined ? JSON.stringify(data) : undefined,
    }),
  put: <T = any>(path: string, data?: unknown) =>
    request<T>(path, {
      method: 'PUT',
      body: data !== undefined ? JSON.stringify(data) : undefined,
    }),
  delete: <T = any>(path: string) => request<T>(path, { method: 'DELETE' }),
};

export default api;
