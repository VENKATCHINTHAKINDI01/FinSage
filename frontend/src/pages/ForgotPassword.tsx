import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Mail, ArrowRight, Loader2, CheckCircle2, ArrowLeft } from 'lucide-react';
import AuthLayout from '../components/layout/AuthLayout';

export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError('Enter a valid email address');
      return;
    }

    setSubmitting(true);
    await new Promise((r) => setTimeout(r, 700)); // demo latency
    setSubmitting(false);
    setSent(true);
  };

  if (sent) {
    return (
      <AuthLayout title="Check your inbox" subtitle="">
        <div className="flex flex-col items-center text-center py-4">
          <div className="w-14 h-14 rounded-full bg-teal-soft text-teal flex items-center justify-center mb-4">
            <CheckCircle2 size={26} />
          </div>
          <p className="text-[13.5px] text-ink font-medium mb-1.5">Reset link sent</p>
          <p className="text-[12.5px] text-ink-soft max-w-xs mb-6">
            If an account exists for <span className="font-medium text-ink">{email}</span>, you'll
            receive password reset instructions shortly.
          </p>
          <Link to="/login" className="inline-flex items-center gap-1.5 text-[12.5px] font-medium text-primary-500 hover:text-primary-600">
            <ArrowLeft size={14} /> Back to sign in
          </Link>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Reset your password" subtitle="Enter your email and we'll send you a reset link">
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {error && <p className="text-[12.5px] text-danger">{error}</p>}

        <div>
          <label className="block text-[12.5px] font-medium text-ink mb-1.5">Email address</label>
          <div className="relative">
            <Mail size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-soft" />
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full h-11 pl-10 pr-3 rounded-xl2 border border-line focus:border-primary-500 text-[13.5px] outline-none transition-colors text-ink bg-white dark:bg-slate-900 dark:text-white"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="w-full h-11 rounded-xl2 bg-primary-500 hover:bg-primary-600 text-white text-[13.5px] font-semibold flex items-center justify-center gap-2 transition-colors disabled:opacity-60 cursor-pointer"
        >
          {submitting ? <Loader2 size={16} className="animate-spin" /> : <>Send reset link <ArrowRight size={15} /></>}
        </button>

        <p className="text-center text-[12.5px] text-ink-soft pt-2">
          <Link to="/login" className="font-medium text-primary-500 hover:text-primary-600 inline-flex items-center gap-1">
            <ArrowLeft size={13} /> Back to sign in
          </Link>
        </p>
      </form>
    </AuthLayout>
  );
}
