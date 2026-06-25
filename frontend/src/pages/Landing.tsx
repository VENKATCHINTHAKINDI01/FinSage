import React from 'react';
import { Link } from 'react-router-dom';

export const Landing: React.FC = () => {
  return (
    <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center p-6 text-center">
      <div className="max-w-3xl space-y-8">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-slate-900 border border-slate-800 text-secondary text-sm font-medium mb-4">
          ✨ Step into the Future of Wealth
        </div>
        <h1 className="text-5xl md:text-7xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-white via-slate-200 to-primary tracking-tight leading-none">
          FinSage AI
        </h1>
        <p className="text-lg md:text-xl text-slate-400 max-w-2xl mx-auto leading-relaxed">
          Intelligent financial optimization, India-specific tax structures, compliance audits, and automated insights powered by agentic intelligence.
        </p>
        
        <div className="flex flex-wrap items-center justify-center gap-4 pt-4">
          <Link to="/login" className="px-8 py-3.5 bg-primary hover:bg-primary-dark text-white font-medium rounded-xl transition-all duration-200 shadow-lg shadow-primary/20 transform hover:-translate-y-0.5">
            Log In
          </Link>
          <Link to="/register" className="px-8 py-3.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-200 font-medium rounded-xl transition-all duration-200 transform hover:-translate-y-0.5">
            Get Started
          </Link>
        </div>
      </div>
    </div>
  );
};

export default Landing;
