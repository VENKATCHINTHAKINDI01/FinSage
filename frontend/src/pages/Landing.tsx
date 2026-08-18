import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import InteractiveCanvas from '../components/common/InteractiveCanvas';
import ParticleField from '../components/common/ParticleField';
import ThemeToggle from '../components/common/ThemeToggle';
import HeroOrb from '../components/three/HeroOrb';
import { Shield, FileText, Calculator, ArrowRight, CheckCircle, TrendingUp, Sparkles } from 'lucide-react';

/* ── Animated Counter Hook ────────────────────────────────────────── */
function useCountUp(target: number, duration = 2000, startOnView = true) {
  const [count, setCount] = useState(0);
  const [started, setStarted] = useState(!startOnView);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!startOnView) return;
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setStarted(true); },
      { threshold: 0.3 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [startOnView]);

  useEffect(() => {
    if (!started) return;
    let start = 0;
    const step = target / (duration / 16);
    const timer = setInterval(() => {
      start += step;
      if (start >= target) {
        setCount(target);
        clearInterval(timer);
      } else {
        setCount(Math.floor(start));
      }
    }, 16);
    return () => clearInterval(timer);
  }, [started, target, duration]);

  return { count, ref };
}

/* ── Scroll Reveal Hook ───────────────────────────────────────────── */
function useScrollReveal() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          el.classList.add('visible');
        }
      },
      { threshold: 0.15, rootMargin: '0px 0px -50px 0px' }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return ref;
}

/* ── What's actually true ─────────────────────────────────────────────
 * Real, verifiable facts about the engine — not usage metrics. FinSage has
 * no users yet to report a count for, and the honest version of this
 * section is a stronger sell for a tax product than an invented one: this
 * is the same "no fabricated figure" rule the product itself enforces,
 * applied to its own marketing page. */
const STATS = [
  { label: 'Financial Years Covered', value: 3, prefix: '', suffix: '', icon: Sparkles, glow: 'stat-glow-cyan', detail: 'FY 2024–25 through FY 2026–27' },
  { label: 'Engine Test Cases', value: 950, prefix: '', suffix: '+', icon: CheckCircle, glow: 'stat-glow-emerald', detail: 'Golden + property-based, 100% passing' },
  { label: 'LLM-Computed Figures', value: 0, prefix: '', suffix: '', icon: Shield, glow: 'stat-glow-violet', detail: 'Every number traced to a deterministic tool result' },
  { label: 'Rule Source', value: 1, prefix: '', suffix: '', icon: TrendingUp, glow: 'stat-glow-amber', detail: 'One versioned rule pack per year, not a model’s guess' },
];

/* ── What makes this different ────────────────────────────────────────
 * Real product principles, not invented customer quotes. Pre-launch, so
 * there are no testimonials to show — and a fabricated one is the exact
 * failure mode this product exists to eliminate, applied to itself. */
const PRINCIPLES = [
  { name: 'The governing rule', role: 'Applies to every number on this site and in the app', text: 'No rupee figure shown to a user may originate from a language model. Every figure is computed by deterministic code from a versioned rule pack, and carries a citation back to its section and source.', avatar: '§' },
  { name: 'Closed windows, stated', role: 'Not hidden', text: 'A benefit that has expired is shown as expired, with the date it closed — not silently omitted and not offered as if it were still open.', avatar: '✓' },
  { name: 'Evidence, not a black box', role: 'Every computation', text: 'Every result comes with a worksheet you can hand to a CA: the inputs, the section cited, the rule-pack version, and the date it was last verified against an official source.', avatar: '📄' },
];

/* One stat tile per component instance — `useCountUp` must be called at a
 * hook's own top level, not inside the .map() callback that used to hold it
 * (that "worked" only because STATS has a fixed length; the rule exists for
 * when it doesn't). */
function StatTile({ stat }: { stat: (typeof STATS)[number] }) {
  const { count, ref } = useCountUp(stat.value);
  return (
    <div ref={ref} className={`card-cosmic p-6 text-center ${stat.glow}`}>
      <stat.icon className="w-8 h-8 mx-auto mb-3 text-cosmic-cyan dark:text-cosmic-cyan" />
      <div className="text-3xl md:text-4xl font-black text-slate-900 dark:text-white font-heading animate-counter">
        {stat.prefix}{count.toLocaleString()}{stat.suffix}
      </div>
      <p className="text-sm text-slate-500 dark:text-slate-400 mt-2 font-medium">{stat.label}</p>
      <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">{stat.detail}</p>
    </div>
  );
}

export const Landing: React.FC = () => {
  const sectionReveal1 = useScrollReveal();
  const sectionReveal2 = useScrollReveal();
  const sectionReveal3 = useScrollReveal();
  const [activePrinciple, setActivePrinciple] = useState(0);

  // Auto-rotate principles
  useEffect(() => {
    const timer = setInterval(() => {
      setActivePrinciple(prev => (prev + 1) % PRINCIPLES.length);
    }, 5000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 flex flex-col relative overflow-hidden transition-colors duration-300">
      {/* Interactive Background */}
      <InteractiveCanvas />
      <div className="dark:hidden">
        {/* Light mode: subtle particle grid */}
        <div className="particle-grid" />
      </div>
      <div className="hidden dark:block">
        <ParticleField theme="ocean" count={45} />
      </div>

      {/* Decorative Blur Orbs */}
      <div className="absolute top-[-20%] left-[-10%] w-[600px] h-[600px] bg-primary/10 dark:bg-cosmic-cyan/5 rounded-full blur-[120px] pointer-events-none animate-float"></div>
      <div className="absolute bottom-[-10%] right-[-10%] w-[600px] h-[600px] bg-secondary/15 dark:bg-cosmic-violet/5 rounded-full blur-[120px] pointer-events-none animate-float" style={{ animationDelay: '-4s' }}></div>

      {/* ── Navigation Header ──────────────────────────────────────── */}
      <header className="relative z-10 w-full max-w-7xl mx-auto px-6 py-5 flex items-center justify-between">
        <div className="flex items-center gap-3 animate-gravity-left" style={{ animationDelay: '0.1s' }}>
          <div className="h-10 w-10 bg-gradient-to-tr from-primary to-cosmic-cyan rounded-xl flex items-center justify-center font-heading font-extrabold text-white shadow-lg shadow-primary/20">
            FS
          </div>
          <span className="font-heading font-extrabold text-2xl tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-slate-900 to-slate-600 dark:from-white dark:to-slate-400">
            FinSage AI
          </span>
        </div>
        
        <div className="flex items-center gap-4 animate-gravity-right" style={{ animationDelay: '0.1s' }}>
          <ThemeToggle />
          <Link 
            to="/login" 
            className="px-5 py-2.5 bg-slate-900 hover:bg-slate-800 dark:bg-slate-900 dark:hover:bg-slate-800 text-white dark:text-slate-100 font-semibold text-sm rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm transition-all duration-300 hover:scale-105"
          >
            Log In
          </Link>
        </div>
      </header>

      {/* ── Hero Section ───────────────────────────────────────────── */}
      <main className="relative z-10 flex-1 flex flex-col items-center max-w-7xl w-full mx-auto px-6 py-12 text-center">
        {/* The one selective 3D accent — desktop only, decorative, behind
            the text (z-0 vs the text's z-10), and self-disables via
            HeroOrb's capability checks. */}
        <div className="hidden lg:block absolute right-[2%] top-[4%] w-[380px] h-[380px] opacity-70 dark:opacity-90 z-0">
          <HeroOrb />
        </div>

        <div className="relative z-10 max-w-4xl space-y-6 animate-gravity-up">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-slate-200/50 dark:bg-slate-900/60 border border-slate-300/40 dark:border-slate-800 text-secondary dark:text-cosmic-cyan text-xs font-semibold uppercase tracking-wider mb-2 backdrop-blur-md aurora-border">
            ✨ India's Advanced Agentic Tax & Revenue Optimization Platform
          </div>
          
          <h1 className="text-5xl sm:text-6xl md:text-8xl font-black tracking-tight leading-none">
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-slate-950 via-slate-800 to-slate-600 dark:from-white dark:via-slate-200 dark:to-slate-400">
              Simplify Taxes.
            </span>
            <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary to-cosmic-cyan dark:from-cosmic-cyan dark:to-cosmic-violet animate-gradient bg-[length:200%_200%]">
              Elevate Wealth.
            </span>
          </h1>
          
          <p className="text-base sm:text-lg md:text-xl text-slate-600 dark:text-slate-400 max-w-2xl mx-auto leading-relaxed">
            Autonomous agentic intelligence tailored for Indian tax compliance, deduction audits, ITR filing steps, and multi-source financial score indexing and maximization.
          </p>
        </div>

        {/* CTA Buttons */}
        <div className="flex flex-wrap items-center justify-center gap-4 relative z-20 mt-10 animate-gravity-up" style={{ animationDelay: '0.2s' }}>
          <Link 
            to="/register" 
            className="px-8 py-4 bg-gradient-to-r from-primary to-cosmic-cyan hover:from-cosmic-cyan hover:to-cosmic-violet text-white font-bold rounded-xl shadow-lg shadow-primary/20 hover:shadow-cosmic-cyan/30 transition-all duration-300 transform hover:-translate-y-0.5 flex items-center gap-2"
          >
            Get Started Now
            <ArrowRight className="w-5 h-5" />
          </Link>
          <Link 
            to="/login" 
            className="px-8 py-4 bg-white hover:bg-slate-100 dark:bg-slate-900 dark:hover:bg-slate-800 text-slate-800 dark:text-slate-200 border border-slate-200 dark:border-slate-800 font-bold rounded-xl transition-all duration-300 transform hover:-translate-y-0.5 shadow-sm"
          >
            Verify Credentials
          </Link>
        </div>

        {/* ── Feature Cards ────────────────────────────────────────── */}
        <div ref={sectionReveal1} className="reveal-on-scroll grid grid-cols-1 md:grid-cols-3 gap-6 w-full pt-16">
          {[
            { icon: Shield, title: 'Compliance Auditor', desc: 'Real-time scans for India-specific regulatory flags. Instantly audits status to maximize verification readiness.', color: 'primary', glow: 'glow-primary' },
            { icon: FileText, title: 'ITR Assistant Agent', desc: 'Tailored support for forms (ITR-1, 2, 4, 5). Guides validation for TDS, advance taxes, and key deadlines.', color: 'cosmic-cyan', glow: 'glow-teal' },
            { icon: Calculator, title: 'Advanced Tax Calculator', desc: 'Aggregates capital gains, business logs, and set-offs. Delivers instant optimizations for GST and cess.', color: 'cosmic-emerald', glow: 'glow-saffron' },
          ].map((card, i) => (
            <div
              key={card.title}
              className={`card-cosmic p-6 space-y-4 text-left ${card.glow}`}
              style={{ animationDelay: `${0.1 + i * 0.1}s` }}
            >
              <div className={`p-3 bg-${card.color}/10 text-${card.color} rounded-xl w-fit`}>
                <card.icon className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-bold text-slate-900 dark:text-white">{card.title}</h3>
              <p className="text-slate-600 dark:text-slate-400 text-sm">{card.desc}</p>
            </div>
          ))}
        </div>

        {/* ── Stats Section — real facts about the engine, not usage
             metrics no one has collected yet ─────────────────────────── */}
        <div ref={sectionReveal2} className="reveal-on-scroll w-full pt-20">
          <h2 className="text-3xl md:text-4xl font-black text-center mb-3 bg-clip-text text-transparent bg-gradient-to-r from-slate-900 to-slate-600 dark:from-white dark:to-slate-400">
            Built to be checked, not trusted blindly
          </h2>
          <p className="text-center text-slate-500 dark:text-slate-400 max-w-xl mx-auto mb-12 text-sm">
            No usage numbers here — FinSage is pre-launch. These are facts about the engine itself.
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            {STATS.map((stat) => (
              <StatTile key={stat.label} stat={stat} />
            ))}
          </div>
        </div>

        {/* ── Principles — what makes this different, in the product's
             own words, not an invented customer quote ─────────────────── */}
        <div ref={sectionReveal3} className="reveal-on-scroll w-full pt-20 pb-10 max-w-3xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-black text-center mb-12 bg-clip-text text-transparent bg-gradient-to-r from-slate-900 to-slate-600 dark:from-white dark:to-slate-400">
            What makes this different
          </h2>
          <div className="relative">
            {PRINCIPLES.map((t, i) => (
              <div
                key={t.name}
                className={`card-cosmic p-8 transition-all duration-500 ${
                  i === activePrinciple
                    ? 'opacity-100 scale-100 translate-y-0'
                    : 'opacity-0 scale-95 translate-y-4 absolute inset-0 pointer-events-none'
                }`}
              >
                <p className="text-lg text-slate-700 dark:text-slate-300 leading-relaxed mb-6">
                  {t.text}
                </p>
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-full bg-gradient-to-br from-cosmic-cyan to-cosmic-violet flex items-center justify-center text-white font-bold text-sm">
                    {t.avatar}
                  </div>
                  <div>
                    <p className="font-bold text-slate-900 dark:text-white">{t.name}</p>
                    <p className="text-sm text-slate-500 dark:text-slate-400">{t.role}</p>
                  </div>
                </div>
              </div>
            ))}
            {/* Dots indicator */}
            <div className="flex justify-center gap-2 mt-6">
              {PRINCIPLES.map((_, i) => (
                <button
                  key={i}
                  onClick={() => setActivePrinciple(i)}
                  className={`w-2.5 h-2.5 rounded-full transition-all duration-300 ${
                    i === activePrinciple
                      ? 'bg-cosmic-cyan w-7'
                      : 'bg-slate-300 dark:bg-slate-700 hover:bg-slate-400'
                  }`}
                />
              ))}
            </div>
          </div>
        </div>
      </main>

      {/* ── Wave Separator ──────────────────────────────────────── */}
      <div className="wave-separator" />

      {/* ── Footer ──────────────────────────────────────────────── */}
      <footer className="relative z-10 w-full max-w-7xl mx-auto px-6 py-8 text-center">
        <div className="border-t border-slate-200/50 dark:border-slate-800 pt-6">
          <p className="text-xs text-slate-500 dark:text-slate-600">
            © 2026 FinSage AI Inc. Developed by Venkat Chinthakindi.
          </p>
          <p className="text-xs text-slate-400 dark:text-slate-700 mt-1">
            Powered by Agentic AI • Data Validated & Cross-Checked
          </p>
        </div>
      </footer>
    </div>
  );
};

export default Landing;
