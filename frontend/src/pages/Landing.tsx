import React from 'react';
import { Link } from 'react-router-dom';
import InteractiveCanvas from '../components/common/InteractiveCanvas';
import ThemeToggle from '../components/common/ThemeToggle';
import { Shield, FileText, Calculator, ArrowRight } from 'lucide-react';

export const Landing: React.FC = () => {
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 flex flex-col justify-between relative overflow-hidden transition-colors duration-300">
      {/* Interactive Background Dotted Waves */}
      <InteractiveCanvas />

      {/* Decorative Blur Orbs */}
      <div className="absolute top-[-20%] left-[-10%] w-[600px] h-[600px] bg-primary/10 dark:bg-primary/5 rounded-full blur-[120px] pointer-events-none animate-float"></div>
      <div className="absolute bottom-[-10%] right-[-10%] w-[600px] h-[600px] bg-secondary/15 dark:bg-secondary/5 rounded-full blur-[120px] pointer-events-none animate-float" style={{ animationDelay: '-4s' }}></div>

      {/* Navigation Header */}
      <header className="relative z-10 w-full max-w-7xl mx-auto px-6 py-5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 bg-gradient-to-tr from-primary to-secondary rounded-xl flex items-center justify-center font-heading font-extrabold text-white shadow-lg shadow-primary/20">
            FS
          </div>
          <span className="font-heading font-extrabold text-2xl tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-slate-900 to-slate-600 dark:from-white dark:to-slate-400">
            FinSage AI
          </span>
        </div>
        
        <div className="flex items-center gap-4">
          <ThemeToggle />
          <Link 
            to="/login" 
            className="px-5 py-2.5 bg-slate-900 hover:bg-slate-800 dark:bg-slate-900 dark:hover:bg-slate-800 text-white dark:text-slate-100 font-semibold text-sm rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm transition-all duration-300 hover:scale-105"
          >
            Log In
          </Link>
        </div>
      </header>

      {/* Hero Section */}
      <main className="relative z-10 flex-1 flex flex-col items-center justify-center max-w-7xl w-full mx-auto px-6 py-12 text-center space-y-12">
        <div className="max-w-4xl space-y-6">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-slate-200/50 dark:bg-slate-900/60 border border-slate-300/40 dark:border-slate-800 text-secondary dark:text-secondary text-xs font-semibold uppercase tracking-wider mb-2 backdrop-blur-md">
            ✨ India’s Advanced Agentic Tax & Revenue Optimization Platform
          </div>
          
          <h1 className="text-5xl sm:text-6xl md:text-8xl font-black tracking-tight leading-none">
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-slate-950 via-slate-800 to-slate-600 dark:from-white dark:via-slate-200 dark:to-slate-400">
              Simplify Taxes.
            </span>
            <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary to-secondary">
              Elevate Wealth.
            </span>
          </h1>
          
          <p className="text-base sm:text-lg md:text-xl text-slate-600 dark:text-slate-400 max-w-2xl mx-auto leading-relaxed">
            Autonomous agentic intelligence tailored for Indian tax compliance, deduction audits, ITR filing steps, and multi-source financial score indexing and maximization.
          </p>
        </div>

        {/* CTA Buttons */}
        <div className="flex flex-wrap items-center justify-center gap-4 relative z-20">
          <Link 
            to="/register" 
            className="px-8 py-4 bg-gradient-to-r from-primary to-primary-dark hover:from-primary-dark hover:to-primary text-white font-bold rounded-xl shadow-lg shadow-primary/20 hover:shadow-primary/30 transition-all duration-300 transform hover:-translate-y-0.5 flex items-center gap-2"
          >
            Get Started Now
            <ArrowRight className="w-5 h-5" />
          </Link>
          <Link 
            to="/login" 
            className="px-8 py-4 bg-white hover:bg-slate-100 dark:bg-slate-900 dark:hover:bg-slate-850 text-slate-800 dark:text-slate-200 border border-slate-200 dark:border-slate-800 font-bold rounded-xl transition-all duration-300 transform hover:-translate-y-0.5 shadow-sm"
          >
            Verify Credentials
          </Link>
        </div>

        {/* Feature Cards Grid (Anti-Gravity Aesthetic) */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full pt-10">
          {/* Card 1 */}
          <div className="bg-white/40 dark:bg-slate-900/40 backdrop-blur-xl border border-slate-200 dark:border-slate-850 p-6 rounded-2xl space-y-4 hover:border-primary/45 dark:hover:border-primary/45 hover:shadow-lg dark:hover:shadow-primary/5 transition-all duration-300 text-left hover:-translate-y-1">
            <div className="p-3 bg-primary/10 text-primary dark:text-primary rounded-xl w-fit">
              <Shield className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-bold text-slate-900 dark:text-white">Compliance Auditor</h3>
            <p className="text-slate-600 dark:text-slate-400 text-sm">
              Real-time scans for India-specific regulatory flags. Instantly audits status to maximize verification readiness.
            </p>
          </div>

          {/* Card 2 */}
          <div className="bg-white/40 dark:bg-slate-900/40 backdrop-blur-xl border border-slate-200 dark:border-slate-850 p-6 rounded-2xl space-y-4 hover:border-secondary/45 dark:hover:border-secondary/45 hover:shadow-lg dark:hover:shadow-secondary/5 transition-all duration-300 text-left hover:-translate-y-1">
            <div className="p-3 bg-secondary/10 text-secondary dark:text-secondary rounded-xl w-fit">
              <FileText className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-bold text-slate-900 dark:text-white">ITR Assistant Agent</h3>
            <p className="text-slate-600 dark:text-slate-400 text-sm">
              Tailored support for forms (ITR-1, 2, 4, 5). Guides validation for TDS, advance taxes, and key deadlines.
            </p>
          </div>

          {/* Card 3 */}
          <div className="bg-white/40 dark:bg-slate-900/40 backdrop-blur-xl border border-slate-200 dark:border-slate-850 p-6 rounded-2xl space-y-4 hover:border-success/45 dark:hover:border-success/45 hover:shadow-lg dark:hover:shadow-success/5 transition-all duration-300 text-left hover:-translate-y-1">
            <div className="p-3 bg-success/10 text-success dark:text-success rounded-xl w-fit">
              <Calculator className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-bold text-slate-900 dark:text-white">Advanced Tax Calculator</h3>
            <p className="text-slate-600 dark:text-slate-400 text-sm">
              Aggregates capital gains, business logs, and set-offs. Delivers instant optimizations for GST and cess.
            </p>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="relative z-10 w-full max-w-7xl mx-auto px-6 py-6 border-t border-slate-200/50 dark:border-slate-900 text-center text-xs text-slate-500 dark:text-slate-600">
        © 2026 FinSage AI Inc. Developed by Venkat Chinthakindi.
      </footer>
    </div>
  );
};

export default Landing;
