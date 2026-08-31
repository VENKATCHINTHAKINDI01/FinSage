import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { login as apiLogin, register as apiRegister, logoutSession } from '../api/services';
import { checkPasswordStrength } from '../utils/password';

/**
 * Authentication state.
 *
 * DEM-001 — what was removed and why
 * -----------------------------------
 * The previous version caught ANY error from the backend — a network blip, a
 * 500, a CORS failure — and silently authenticated the user against a
 * localStorage list of "demo users", issuing a fake token from
 * `btoa(email + ':' + Date.now())` and storing their password IN PLAINTEXT.
 *
 * The failure mode was the dangerous kind: when the backend was down, the app
 * did not look broken. It looked like it had logged you in, and every page then
 * rendered fabricated financial figures indistinguishable from real ones.
 *
 * A finance product must fail visibly. An error state is a worse demo and a far
 * better product.
 */

export interface User {
  name: string;
  email: string;
}

export interface AuthState {
  user: User | null;
  token: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  authError: string | null;
  isSubmitting: boolean;
  login: (p: { email: string; password: string }) => Promise<{ success: boolean; error?: string }>;
  signup: (p: { name: string; email: string; password: string }) => Promise<{ success: boolean; error?: string }>;
  logout: () => void;
  clearError: () => void;
}

/** Surface the real reason, without leaking internals. */
function describe(err: unknown): string {
  const message = err instanceof Error ? err.message : String(err ?? '');
  if (/failed to fetch|networkerror|load failed/i.test(message)) {
    return 'Could not reach the server. Check your connection and try again.';
  }
  return message || 'Something went wrong. Please try again.';
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      authError: null,
      isSubmitting: false,

      login: async ({ email, password }) => {
        set({ authError: null, isSubmitting: true });
        try {
          const res = await apiLogin(email, password);
          set({
            user: { name: res.name || email.split('@')[0], email },
            token: res.access_token,
            refreshToken: res.refresh_token,
            isAuthenticated: true,
            authError: null,
            isSubmitting: false,
          });
          return { success: true };
        } catch (err) {
          // No fallback. A failed login is a failed login.
          const error = describe(err);
          set({ authError: error, isAuthenticated: false, token: null, refreshToken: null, isSubmitting: false });
          return { success: false, error };
        }
      },

      signup: async ({ name, email, password }) => {
        set({ authError: null, isSubmitting: true });

        const strength = checkPasswordStrength(password);
        if (!strength.meetsMinimum) {
          const error = 'Password does not meet the minimum strength requirements.';
          set({ authError: error, isSubmitting: false });
          return { success: false, error };
        }

        try {
          const res = await apiRegister({ name, email, password });
          set({
            user: { name, email },
            token: res.access_token,
            refreshToken: res.refresh_token,
            isAuthenticated: true,
            authError: null,
            isSubmitting: false,
          });
          return { success: true };
        } catch (err) {
          const error = describe(err);
          set({ authError: error, isAuthenticated: false, token: null, refreshToken: null, isSubmitting: false });
          return { success: false, error };
        }
      },

      logout: () => {
        // Best-effort: revoke the session family server-side so the refresh
        // token can't still be used after logout. Was pure local state
        // clearing before — the token stayed valid on the backend until its
        // natural expiry regardless of "logging out" in the UI. Fire it
        // without awaiting; the local session ends immediately either way.
        const rt = get().refreshToken;
        if (rt) {
          logoutSession(rt).catch(() => {
            /* already-invalid or unreachable — nothing to react to, this
               was PURELY to revoke the token, the client's own state is
               cleared unconditionally below */
          });
        }
        set({ user: null, token: null, refreshToken: null, isAuthenticated: false, authError: null });
      },

      clearError: () => set({ authError: null }),
    }),
    {
      name: 'finsage_auth',
      // Only what is needed to restore a session. Never a password, and no
      // demo-mode flag, because there is no longer a demo mode.
      partialize: (state) => ({
        user: state.user,
        token: state.token,
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated,
      }),
      version: 2,
      // Clear any credentials the previous build left in this browser.
      migrate: (persisted, version) => {
        const empty = { user: null, token: null, refreshToken: null, isAuthenticated: false };
        if (version < 2) {
          // Purge credentials the previous build stored in this browser.
          try {
            localStorage.removeItem('finsage_demo_users');
          } catch {
            /* storage unavailable — nothing to clean */
          }
          return empty;
        }
        const s = persisted as Partial<AuthState> | undefined;
        return {
          user: s?.user ?? null,
          token: s?.token ?? null,
          // Sessions persisted before refresh support simply never had this
          // key — falls back to null, which correctly forces a real login
          // rather than a synthesized token.
          refreshToken: s?.refreshToken ?? null,
          isAuthenticated: s?.isAuthenticated ?? false,
        };
      },
    }
  )
);

// Wired up to events client.ts already dispatched but that nothing listened
// for, so a 401 never actually ended the session — every open page just
// broke into generic error states while isAuthenticated stayed true.
if (typeof window !== 'undefined') {
  // client.ts refreshed silently and rewrote localStorage directly (it
  // cannot import this store — this store imports the API layer that
  // imports client.ts, and that would be a cycle). Mirror the new tokens
  // into in-memory state so a component reading `token` isn't stale.
  window.addEventListener('auth-tokens-refreshed', (e) => {
    const detail = (e as CustomEvent<{ token: string; refreshToken: string }>).detail;
    if (detail) useAuthStore.setState({ token: detail.token, refreshToken: detail.refreshToken });
  });

  // Refresh was attempted and failed (no refresh token, or it was rejected)
  // — the session is genuinely over. Clearing isAuthenticated here is what
  // makes ProtectedRoute actually redirect to /login.
  window.addEventListener('auth-unauthorized', () => {
    useAuthStore.setState({ user: null, token: null, refreshToken: null, isAuthenticated: false });
  });
}
