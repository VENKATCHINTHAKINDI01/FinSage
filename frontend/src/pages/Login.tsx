import React, { useState } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { useAppDispatch } from '../store/store';
import { loginSuccess } from '../store/slices/authSlice';
import InteractiveCanvas from '../components/common/InteractiveCanvas';
import ThemeToggle from '../components/common/ThemeToggle';
import { ArrowLeft } from 'lucide-react';

export const Login: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const location = useLocation();

  const from = location.state?.from?.pathname || '/dashboard';

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (email && password) {
      // Mock successful login
      const mockToken = "mock-jwt-token-123";
      const mockUser = { id: "user-123", email, fullName: "Demo User" };
      
      sessionStorage.setItem('token', mockToken);
      dispatch(loginSuccess({ token: mockToken, user: mockUser }));
      
      navigate(from, { replace: true });
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 flex flex-col items-center justify-center p-6 relative overflow-hidden transition-colors duration-300">
      {/* Dynamic Dotted Waves Background */}
      <InteractiveCanvas />

      {/* Decorative gradients */}
      <div className="absolute top-[-10%] left-[-10%] w-96 h-96 bg-primary/10 dark:bg-primary/5 rounded-full blur-3xl pointer-events-none"></div>
      <div className="absolute bottom-[-10%] right-[-10%] w-96 h-96 bg-secondary/10 dark:bg-secondary/5 rounded-full blur-3xl pointer-events-none"></div>

      {/* Top Header Actions */}
      <div className="absolute top-6 left-6 right-6 flex items-center justify-between z-20">
        <Link 
          to="/" 
          className="flex items-center gap-2 px-3 py-1.5 text-sm font-semibold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Home
        </Link>
        <ThemeToggle />
      </div>

      {/* Glassmorphic Auth Form */}
      <div className="w-full max-w-md bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl border border-slate-200 dark:border-slate-800 rounded-2xl p-8 space-y-6 shadow-2xl relative z-10 transition-colors duration-300">
        <div className="space-y-2 text-center">
          <div className="inline-flex h-9 w-9 bg-gradient-to-tr from-primary to-secondary rounded-lg items-center justify-center font-heading font-bold text-white mb-2 shadow-md">
            FS
          </div>
          <h2 className="text-3xl font-black text-slate-950 dark:text-white">Welcome Back</h2>
          <p className="text-slate-500 dark:text-slate-400 text-sm">Sign in to your FinSage AI account</p>
        </div>
        
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <label className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">Email Address</label>
            <input 
              type="email" 
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-4 py-3 bg-white/90 dark:bg-slate-950/80 border border-slate-250 dark:border-slate-800 rounded-xl focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-600 input-glow transition-all duration-200"
            placeholder="vyas@example.com"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">Password</label>
            <input 
              type="password" 
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-3 bg-white/90 dark:bg-slate-950/80 border border-slate-250 dark:border-slate-800 rounded-xl focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-600 input-glow transition-all duration-200"
              placeholder="••••••••"
            />
          </div>
          
          <button 
            type="submit"
            className="w-full py-3.5 bg-gradient-to-r from-primary to-primary-dark hover:from-primary-dark hover:to-primary text-white font-bold rounded-xl shadow-lg shadow-primary/10 hover:shadow-primary/20 transition-all duration-300 transform hover:-translate-y-0.5 mt-2 cursor-pointer"
          >
            Log In
          </button>
        </form>

        <div className="text-center pt-2">
          <p className="text-slate-500 dark:text-slate-400 text-sm">
            Don't have an account?{' '}
            <Link to="/register" className="text-primary hover:underline font-bold transition-all">
              Sign Up
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default Login;
