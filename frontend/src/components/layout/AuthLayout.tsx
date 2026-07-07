import React from 'react';
import { IndianRupee, ShieldCheck, Sparkles, TrendingUp } from 'lucide-react';
import CosmicBackground from '../common/CosmicBackground';

const HIGHLIGHTS = [
  { icon: ShieldCheck, text: 'India-specific compliance & audit-readiness checks' },
  { icon: TrendingUp, text: 'Live tax optimization across 80C, 80D, NPS & more' },
  { icon: Sparkles, text: 'AI agents that read your Form 16, 26AS, and GST data' },
];

interface AuthLayoutProps {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}

export default function AuthLayout({ title, subtitle, children }: AuthLayoutProps) {
  return (
    <div className="min-h-screen w-full grid grid-cols-1 lg:grid-cols-2 bg-slate-50 dark:bg-slate-950 relative overflow-hidden transition-colors duration-300">
      {/* Interactive bubble background behind both panels */}
      <CosmicBackground mode="ocean" />

      {/* Brand panel */}
      <div className="hidden lg:flex flex-col justify-between bg-gradient-to-br from-navy/90 to-navy-deep/95 text-white p-12 relative overflow-hidden backdrop-blur-md border-r border-white/5 z-10">
        <div className="absolute -right-24 -top-24 w-96 h-96 rounded-full bg-gradient-to-br from-saffron/20 to-teal/10 blur-3xl" />
        <div className="absolute -left-16 bottom-0 w-72 h-72 rounded-full bg-gradient-to-tr from-primary-500/20 to-transparent blur-3xl animate-float-slow" />

        <div className="relative flex items-center gap-2.5 animate-fade-in">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-saffron to-teal flex items-center justify-center shadow-lg shadow-teal/20">
            <IndianRupee size={18} strokeWidth={2.5} className="text-white" />
          </div>
          <span className="font-display font-semibold text-[17px] tracking-tight">FinSage AI</span>
        </div>

        <div className="relative space-y-2 animate-slide-up">
          <p className="font-display font-semibold text-[32px] leading-tight mb-4 max-w-md">
            Financial intelligence,<br />built for India's tax code.
          </p>
          <p className="text-white/60 text-[14px] max-w-sm mb-10 leading-relaxed">
            One platform for tax optimization, compliance, ITR filing, and financial health —
            grounded in FY 2024–25 rules.
          </p>

          <div className="space-y-4 pt-2">
            {HIGHLIGHTS.map(({ icon: Icon, text }, i) => (
              <div key={i} className="flex items-center gap-3 group">
                <div className="w-8 h-8 rounded-lg bg-white/10 flex items-center justify-center shrink-0 transition-transform group-hover:scale-110 duration-200">
                  <Icon size={15} />
                </div>
                <p className="text-[13px] text-white/80 transition-colors group-hover:text-white">{text}</p>
              </div>
            ))}
          </div>
        </div>

        <p className="relative text-[11.5px] text-white/40 animate-fade-in">© 2026 FinSage AI · Built for FY 2024–25</p>
      </div>

      {/* Form panel with Premium Glassmorphism card container */}
      <div className="relative z-10 flex items-center justify-center p-6 sm:p-10">
        <div className="w-full max-w-[430px] p-8 sm:p-10 rounded-[24px] border border-white/40 dark:border-slate-800/40 bg-white/70 dark:bg-slate-900/65 backdrop-blur-xl shadow-xl shadow-slate-100/50 dark:shadow-none animate-rise">
          <div className="lg:hidden flex items-center gap-2.5 mb-8">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-saffron to-teal flex items-center justify-center">
              <IndianRupee size={16} strokeWidth={2.5} className="text-white" />
            </div>
            <span className="font-display font-semibold text-[16px] tracking-tight text-ink">FinSage AI</span>
          </div>

          <h1 className="font-display font-semibold text-[24px] text-ink mb-1.5">{title}</h1>
          <p className="text-[13.5px] text-ink-soft mb-8">{subtitle}</p>

          {children}
        </div>
      </div>
    </div>
  );
}

