import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Eye, EyeOff, Mail, Lock, User, AlertCircle, Loader2, ArrowRight, Check } from 'lucide-react';
import AuthLayout from '../components/layout/AuthLayout';
import PasswordStrengthMeter from '../components/ui/PasswordStrengthMeter';
import { useAuthStore } from '../store/useAuthStore';
import { checkPasswordStrength } from '../utils/password';

export default function Signup() {
  const navigate = useNavigate();
  const signup = useAuthStore((s) => s.signup);

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string | null>>({});

  const strength = checkPasswordStrength(password);

  const validate = () => {
    const errs: Record<string, string> = {};
    if (!name.trim()) errs.name = 'Full name is required';
    if (!email) errs.email = 'Email is required';
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errs.email = 'Enter a valid email address';
    if (!password) errs.password = 'Password is required';
    else if (!strength.meetsMinimum) errs.password = 'Password does not meet the strength requirements below';
    if (confirmPassword !== password) errs.confirmPassword = 'Passwords do not match';
    if (!agreedToTerms) errs.terms = 'You must accept the terms to continue';
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!validate()) return;

    setSubmitting(true);
    const result = await signup({ name: name.trim(), email, password });
    setSubmitting(false);

    if (result.success) {
      navigate('/dashboard', { replace: true });
    } else {
      setError(result.error || 'Something went wrong. Please try again.');
    }
  };

  return (
    <AuthLayout title="Create your account" subtitle="Set up FinSage AI for the FY 2024–25 filing season">
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {error && (
          <div className="flex items-start gap-2.5 p-3 rounded-xl2 bg-red-50 border border-danger/20 animate-rise">
            <AlertCircle size={16} className="text-danger shrink-0 mt-0.5" />
            <p className="text-[12.5px] text-danger leading-snug">{error}</p>
          </div>
        )}

        <div>
          <label className="block text-[12.5px] font-medium text-ink mb-1.5">Full name</label>
          <div className="relative">
            <User size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-soft" />
            <input
              type="text"
              value={name}
              onChange={(e) => { setName(e.target.value); setFieldErrors((f) => ({ ...f, name: null })); }}
              placeholder="Venkat Chinthakindi"
              autoComplete="name"
              className={`w-full h-11 pl-10 pr-3 rounded-xl2 border text-[13.5px] outline-none transition-colors text-ink bg-white dark:bg-slate-900 dark:text-white ${
                fieldErrors.name ? 'border-danger' : 'border-line focus:border-primary-500'
              }`}
            />
          </div>
          {fieldErrors.name && <p className="text-[11.5px] text-danger mt-1">{fieldErrors.name}</p>}
        </div>

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
          <label className="block text-[12.5px] font-medium text-ink mb-1.5">Password</label>
          <div className="relative">
            <Lock size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-soft" />
            <input
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => { setPassword(e.target.value); setFieldErrors((f) => ({ ...f, password: null })); }}
              placeholder="Create a strong password"
              autoComplete="new-password"
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
          <PasswordStrengthMeter password={password} />
        </div>

        <div>
          <label className="block text-[12.5px] font-medium text-ink mb-1.5">Confirm password</label>
          <div className="relative">
            <Lock size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-soft" />
            <input
              type={showPassword ? 'text' : 'password'}
              value={confirmPassword}
              onChange={(e) => { setConfirmPassword(e.target.value); setFieldErrors((f) => ({ ...f, confirmPassword: null })); }}
              placeholder="Re-enter your password"
              autoComplete="new-password"
              className={`w-full h-11 pl-10 pr-10 rounded-xl2 border text-[13.5px] outline-none transition-colors text-ink bg-white dark:bg-slate-900 dark:text-white ${
                fieldErrors.confirmPassword ? 'border-danger' : 'border-line focus:border-primary-500'
              }`}
            />
            {confirmPassword && confirmPassword === password && (
              <Check size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-teal" />
            )}
          </div>
          {fieldErrors.confirmPassword && <p className="text-[11.5px] text-danger mt-1">{fieldErrors.confirmPassword}</p>}
        </div>

        <div>
          <label className="flex items-start gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={agreedToTerms}
              onChange={(e) => { setAgreedToTerms(e.target.checked); setFieldErrors((f) => ({ ...f, terms: null })); }}
              className="w-4 h-4 mt-0.5 rounded accent-primary-500 shrink-0"
            />
            <span className="text-[12px] text-ink-soft leading-snug">
              I agree to the Terms of Service and Privacy Policy, and consent to FinSage AI
              processing my financial data to generate tax and compliance insights.
            </span>
          </label>
          {fieldErrors.terms && <p className="text-[11.5px] text-danger mt-1">{fieldErrors.terms}</p>}
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="w-full h-11 rounded-xl2 bg-primary-500 hover:bg-primary-600 text-white text-[13.5px] font-semibold flex items-center justify-center gap-2 transition-colors disabled:opacity-60 cursor-pointer"
        >
          {submitting ? <Loader2 size={16} className="animate-spin" /> : <>Create account <ArrowRight size={15} /></>}
        </button>

        <p className="text-center text-[12.5px] text-ink-soft pt-2">
          Already have an account?{' '}
          <Link to="/login" className="font-medium text-primary-500 hover:text-primary-600">Sign in</Link>
        </p>
      </form>
    </AuthLayout>
  );
}
