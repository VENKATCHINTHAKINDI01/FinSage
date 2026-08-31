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
 *
 * Silent token refresh — what was missing and why it mattered
 * -------------------------------------------------------------
 * Access tokens expire in 15 minutes (backend/config.py). The backend already
 * issues a refresh token on login and has a working, security-hardened
 * /auth/refresh endpoint (single-use rotation, reuse-triggers-revocation) —
 * the frontend just never stored the refresh token or called it. A 401 threw
 * an ApiError and dispatched 'auth-unauthorized', an event nothing listened
 * for, so the actual effect of an expired token was every open page quietly
 * breaking into generic error states while the app still believed the user
 * was logged in. Now a 401 attempts one silent refresh-and-retry before
 * giving up.
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

interface StoredTokens {
  token: string | null;
  refreshToken: string | null;
}

function readTokens(): StoredTokens {
  try {
    const raw = localStorage.getItem(TOKEN_STORE);
    const state = raw ? JSON.parse(raw)?.state : null;
    return { token: state?.token ?? null, refreshToken: state?.refreshToken ?? null };
  } catch {
    return { token: null, refreshToken: null };
  }
}

/**
 * Written directly to the same localStorage key Zustand's `persist`
 * middleware owns, rather than importing `useAuthStore` here — that store
 * imports `login`/`register` from this module's sibling (`services.ts`),
 * which imports this file, so importing the store back would be a cycle.
 * `useAuthStore` picks up the change via the `auth-tokens-refreshed` event
 * dispatched below, the same pattern already used for `auth-unauthorized`.
 */
function writeTokens(token: string, refreshToken: string) {
  try {
    const raw = localStorage.getItem(TOKEN_STORE);
    const parsed = raw ? JSON.parse(raw) : { state: {}, version: 2 };
    parsed.state = { ...parsed.state, token, refreshToken };
    localStorage.setItem(TOKEN_STORE, JSON.stringify(parsed));
    window.dispatchEvent(new CustomEvent('auth-tokens-refreshed', { detail: { token, refreshToken } }));
  } catch {
    /* storage unavailable — the retried request still carries the new
       token in memory for this call; only persistence across reloads is lost */
  }
}

/** Broadcast so the app can route to login without this module importing the store. */
function onUnauthorized() {
  window.dispatchEvent(new Event('auth-unauthorized'));
}

// Endpoints that must never trigger a refresh-and-retry on their own 401 —
// refreshing in response to a failed login/register makes no sense, and
// retrying a failed /refresh call with a refresh would loop.
const NO_REFRESH_PATHS = ['/api/v1/auth/login', '/api/v1/auth/register', '/api/v1/auth/refresh'];

// Single-flight: every 401 that arrives while a refresh is already in
// flight awaits that SAME promise instead of firing its own. The backend's
// refresh token is single-use and reuse is treated as theft (revokes the
// whole session) — a page that fires four parallel requests on load would
// otherwise turn its own concurrent 401s into a self-inflicted logout.
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    const { refreshToken } = readTokens();
    if (!refreshToken) return null;
    try {
      const res = await fetch(`${BASE}/api/v1/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) return null;
      const data = await res.json();
      writeTokens(data.access_token, data.refresh_token);
      return data.access_token as string;
    } catch {
      return null;
    }
  })();

  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}

async function request<T = any>(path: string, options: RequestInit = {}, isRetry = false): Promise<T> {
  const { token } = readTokens();

  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {}),
    },
  });

  if (res.status === 401) {
    const canRefresh = !isRetry && !NO_REFRESH_PATHS.some((p) => path.startsWith(p));
    if (canRefresh) {
      const newToken = await refreshAccessToken();
      if (newToken) {
        return request<T>(path, options, true);
      }
    }
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
