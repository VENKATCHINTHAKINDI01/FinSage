import React, { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { Eye, EyeOff, Mail, Lock, AlertCircle, Loader2, ArrowRight } from 'lucide-react';
import AuthLayout from '../components/layout/AuthLayout';
import { useAuthStore } from '../store/useAuthStore';

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const login = useAuthStore((s) => s.login);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string | null>>({});

  const validate = () => {
    const errs: Record<string, string> = {};
    if (!email) errs.email = 'Email is required';
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errs.email = 'Enter a valid email address';
    if (!password) errs.password = 'Password is required';
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!validate()) return;

    setSubmitting(true);
    const result = await login({ email, password });
    setSubmitting(false);

    if (result.success) {
      const dest = location.state?.from || '/dashboard';
      navigate(dest, { replace: true });
    } else {
      setError(result.error || 'Something went wrong. Please try again.');
    }
  };

  return (
    <AuthLayout title="Welcome back" subtitle="Sign in to continue to your financial dashboard">
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {error && (
          <div className="flex items-start gap-2.5 p-3 rounded-xl2 bg-red-50 border border-danger/20 animate-rise">
            <AlertCircle size={16} className="text-danger shrink-0 mt-0.5" />
            <p className="text-[12.5px] text-danger leading-snug">{error}</p>
          </div>
        )}

        <div>
          <label className="block text-[12.5px] font-medium text-ink mb-1.5">Email address</label>
          <div className="relative">
            <Mail size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-soft" />
            <input
              type="email"
              value={email}
              onChange={(e) => { setEmail(e.target.value); setFieldErrors((f) => ({ ...f, email: null })); }}
              placeholder="you@example.com"
              autoComplete="email"
              className={`w-full h-11 pl-10 pr-3 rounded-xl2 border text-[13.5px] outline-none transition-colors text-ink bg-white dark:bg-slate-900 dark:text-white ${
                fieldErrors.email ? 'border-danger' : 'border-line focus:border-primary-500'
              }`}
            />
          </div>
          {fieldErrors.email && <p className="text-[11.5px] text-danger mt-1">{fieldErrors.email}</p>}
        </div>

        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="block text-[12.5px] font-medium text-ink">Password</label>
            <Link to="/forgot-password" className="text-[11.5px] font-medium text-primary-500 hover:text-primary-600">
              Forgot password?
            </Link>
          </div>
          <div className="relative">
            <Lock size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-soft" />
            <input
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => { setPassword(e.target.value); setFieldErrors((f) => ({ ...f, password: null })); }}
              placeholder="••••••••"
              autoComplete="current-password"
              className={`w-full h-11 pl-10 pr-10 rounded-xl2 border text-[13.5px] outline-none transition-colors text-ink bg-white dark:bg-slate-900 dark:text-white ${
                fieldErrors.password ? 'border-danger' : 'border-line focus:border-primary-500'
              }`}
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-soft hover:text-ink"
              tabIndex={-1}
            >
              {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
          {fieldErrors.password && <p className="text-[11.5px] text-danger mt-1">{fieldErrors.password}</p>}
        </div>

        <label className="flex items-center gap-2 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
            className="w-4 h-4 rounded accent-primary-500"
          />
          <span className="text-[12.5px] text-ink-soft">Keep me signed in on this device</span>
        </label>

        <button
          type="submit"
          disabled={submitting}
          className="w-full h-11 rounded-xl2 bg-primary-500 hover:bg-primary-600 text-white text-[13.5px] font-semibold flex items-center justify-center gap-2 transition-colors disabled:opacity-60 cursor-pointer"
        >
          {submitting ? <Loader2 size={16} className="animate-spin" /> : <>Sign in <ArrowRight size={15} /></>}
        </button>

        <p className="text-center text-[12.5px] text-ink-soft pt-2">
          Don't have an account?{' '}
          <Link to="/signup" className="font-medium text-primary-500 hover:text-primary-600">Create one</Link>
        </p>
      </form>
    </AuthLayout>
  );
}
