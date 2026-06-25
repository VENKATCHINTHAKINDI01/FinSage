import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAppDispatch } from '../store/store';
import { loginSuccess, loginStart, loginFailure } from '../store/slices/authSlice';
import api from '../services/api';
import InteractiveCanvas from '../components/common/InteractiveCanvas';
import ThemeToggle from '../components/common/ThemeToggle';
import { ArrowLeft } from 'lucide-react';

export const Register: React.FC = () => {
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const dispatch = useAppDispatch();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    setLoading(true);
    dispatch(loginStart());

    try {
      // 1. Post to registration
      await api.post('/auth/register', {
        email,
        full_name: fullName,
        password,
      });

      // 2. Automatically log in after registration
      const loginResponse = await api.post('/auth/login', {
        email,
        password,
      });
      const { access_token } = loginResponse.data;

      // Persist access token in session storage
      sessionStorage.setItem('token', access_token);

      // 3. Fetch authenticated user profile details from /me
      const profileResponse = await api.get('/auth/me');
      const user = profileResponse.data;

      // Dispatch success
      dispatch(loginSuccess({ token: access_token, user }));
      navigate('/dashboard', { replace: true });
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to create account. Please verify password strength.';
      setError(errorMsg);
      dispatch(loginFailure(errorMsg));
    } finally {
      setLoading(false);
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
      <div className="w-full max-w-md bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl border border-slate-200 dark:border-slate-800 rounded-2xl p-8 space-y-5 shadow-2xl relative z-10 transition-colors duration-300">
        <div className="space-y-2 text-center">
          <div className="inline-flex h-9 w-9 bg-gradient-to-tr from-primary to-secondary rounded-lg items-center justify-center font-heading font-bold text-white mb-2 shadow-md">
            FS
          </div>
          <h2 className="text-3xl font-black text-slate-950 dark:text-white">Create Account</h2>
          <p className="text-slate-500 dark:text-slate-400 text-sm">Join FinSage AI and master your taxes</p>
        </div>

        {error && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 text-red-600 dark:text-red-400 text-sm rounded-xl text-center font-medium">
            {error}
          </div>
        )}
        
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="space-y-0.5">
            <label className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">Full Name</label>
            <input 
              type="text" 
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full px-4 py-2.5 bg-white/90 dark:bg-slate-950/80 border border-slate-250 dark:border-slate-800 rounded-xl focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-600 input-glow transition-all duration-200"
              placeholder="Ameer Sohail"
            />
          </div>

          <div className="space-y-0.5">
            <label className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">Email Address</label>
            <input 
              type="email" 
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-4 py-2.5 bg-white/90 dark:bg-slate-950/80 border border-slate-250 dark:border-slate-800 rounded-xl focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-600 input-glow transition-all duration-200"
              placeholder="name@example.com"
            />
          </div>

          <div className="space-y-0.5">
            <label className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">Password</label>
            <input 
              type="password" 
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-2.5 bg-white/90 dark:bg-slate-950/80 border border-slate-250 dark:border-slate-800 rounded-xl focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-600 input-glow transition-all duration-200"
              placeholder="••••••••"
            />
          </div>

          <div className="space-y-0.5">
            <label className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">Confirm Password</label>
            <input 
              type="password" 
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full px-4 py-2.5 bg-white/90 dark:bg-slate-950/80 border border-slate-250 dark:border-slate-800 rounded-xl focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-600 input-glow transition-all duration-200"
              placeholder="••••••••"
            />
          </div>
          
          <button 
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-gradient-to-r from-primary to-primary-dark hover:from-primary-dark hover:to-primary text-white font-bold rounded-xl shadow-lg shadow-primary/10 hover:shadow-primary/20 transition-all duration-300 transform hover:-translate-y-0.5 mt-3 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Creating Account...' : 'Create Account'}
          </button>
        </form>

        <div className="text-center pt-1">
          <p className="text-slate-500 dark:text-slate-400 text-sm">
            Already have an account?{' '}
            <Link to="/login" className="text-primary hover:underline font-bold transition-all">
              Log In
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default Register;
