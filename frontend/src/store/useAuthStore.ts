import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { login as apiLogin, register as apiRegister } from '../api/services';
import { checkPasswordStrength } from '../utils/password';

const DEMO_USERS_KEY = 'finsage_demo_users';

interface DemoUser {
  name: string;
  email: string;
  password?: string;
}

function readDemoUsers(): DemoUser[] {
  try {
    return JSON.parse(localStorage.getItem(DEMO_USERS_KEY) || '[]');
  } catch {
    return [];
  }
}

function writeDemoUsers(users: DemoUser[]) {
  localStorage.setItem(DEMO_USERS_KEY, JSON.stringify(users));
}

function fakeToken(email: string) {
  return btoa(`${email}:${Date.now()}`);
}

export interface User {
  name: string;
  email: string;
  financialYear: string;
}

export interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  authError: string | null;
  isDemoAuth: boolean;
  login: (params: { email: string; password: string }) => Promise<{ success: boolean; error?: string; demo?: boolean }>;
  signup: (params: { name: string; email: string; password: string }) => Promise<{ success: boolean; error?: string; demo?: boolean }>;
  logout: () => void;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      authError: null,
      isDemoAuth: false,

      login: async ({ email, password }) => {
        set({ authError: null });

        try {
          const res = await apiLogin(email, password);
          const user = { name: res.name || email.split('@')[0], email, financialYear: '2024-25' };
          set({ user, token: res.access_token, isAuthenticated: true, isDemoAuth: false, authError: null });
          return { success: true };
        } catch (_) {
          const users = readDemoUsers();
          const match = users.find((u) => u.email.toLowerCase() === email.toLowerCase());

          if (!match) {
            const err = 'No account found with that email. Please sign up first.';
            set({ authError: err });
            return { success: false, error: err };
          }
          if (match.password !== password) {
            const err = 'Incorrect password. Please try again.';
            set({ authError: err });
            return { success: false, error: err };
          }

          const user = { name: match.name, email: match.email, financialYear: '2024-25' };
          set({ user, token: fakeToken(email), isAuthenticated: true, isDemoAuth: true, authError: null });
          return { success: true, demo: true };
        }
      },

      signup: async ({ name, email, password }) => {
        set({ authError: null });

        const strength = checkPasswordStrength(password);
        if (!strength.meetsMinimum) {
          const err = 'Password does not meet the minimum strength requirements.';
          set({ authError: err });
          return { success: false, error: err };
        }

        try {
          const res = await apiRegister({ name, email, password });
          const user = { name, email, financialYear: '2024-25' };
          set({ user, token: res.access_token, isAuthenticated: true, isDemoAuth: false, authError: null });
          return { success: true };
        } catch (_) {
          const users = readDemoUsers();
          if (users.some((u) => u.email.toLowerCase() === email.toLowerCase())) {
            const err = 'An account with this email already exists.';
            set({ authError: err });
            return { success: false, error: err };
          }

          users.push({ name, email, password });
          writeDemoUsers(users);

          const user = { name, email, financialYear: '2024-25' };
          set({ user, token: fakeToken(email), isAuthenticated: true, isDemoAuth: true, authError: null });
          return { success: true, demo: true };
        }
      },

      logout: () => {
        set({ user: null, token: null, isAuthenticated: false, isDemoAuth: false, authError: null });
      },

      clearError: () => set({ authError: null }),
    }),
    {
      name: 'finsage_auth',
      partialize: (state) => ({
        user: state.user,
        token: state.token,
        isAuthenticated: state.isAuthenticated,
        isDemoAuth: state.isDemoAuth,
      }),
    }
  )
);
