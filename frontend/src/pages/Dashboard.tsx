import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppDispatch, useAppSelector } from '../store/store';
import { logout } from '../store/slices/authSlice';
import ThemeToggle from '../components/common/ThemeToggle';
import { 
  TrendingUp, 
  ShieldAlert, 
  FileText, 
  Calculator, 
  LogOut, 
  User, 
  CheckCircle2, 
  AlertTriangle,
  Calendar,
  ArrowUpRight,
  Percent,
  Download
} from 'lucide-react';
import { 
  ResponsiveContainer, 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  Tooltip 
} from 'recharts';

// Mock data for financial health trend
const healthData = [
  { month: 'Jan', score: 68 },
  { month: 'Feb', score: 72 },
  { month: 'Mar', score: 70 },
  { month: 'Apr', score: 78 },
  { month: 'May', score: 85 },
  { month: 'Jun', score: 92 },
];

export const Dashboard: React.FC = () => {
  const { user } = useAppSelector((state) => state.auth);
  const dispatch = useAppDispatch();
  const navigate = useNavigate();

  const handleLogout = () => {
    dispatch(logout());
    navigate('/login');
  };

  const username = user?.fullName || 'Ameer Sohail';

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 flex flex-col font-body relative overflow-hidden transition-colors duration-300">
      {/* Background Gradients */}
      <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-primary/5 rounded-full blur-[100px] pointer-events-none"></div>
      <div className="absolute bottom-0 left-0 w-[500px] h-[500px] bg-secondary/5 rounded-full blur-[100px] pointer-events-none"></div>

      {/* Header */}
      <header className="border-b border-slate-200 dark:border-slate-900 bg-white/80 dark:bg-slate-950/80 backdrop-blur-md sticky top-0 z-40 transition-colors duration-300">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 bg-gradient-to-tr from-primary to-secondary rounded-lg flex items-center justify-center font-heading font-bold text-white shadow-lg shadow-primary/20">
              FS
            </div>
            <span className="font-heading font-extrabold text-xl tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-slate-950 to-slate-600 dark:from-white dark:to-slate-400">
              FinSage AI
            </span>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-sm transition-colors duration-300">
              <User className="h-4 w-4 text-secondary" />
              <span className="text-slate-700 dark:text-slate-300 font-semibold">{username}</span>
            </div>
            
            <ThemeToggle />
            
            <button 
              onClick={handleLogout}
              className="p-2.5 rounded-xl text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-900 border border-slate-200 dark:border-transparent dark:hover:border-slate-800 transition-all duration-200 cursor-pointer"
              title="Sign Out"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8 relative z-10">
        {/* Welcome Section */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 bg-white/60 dark:bg-slate-900/40 p-6 rounded-2xl border border-slate-200 dark:border-slate-900 backdrop-blur-sm transition-colors duration-300">
          <div>
            <h1 className="text-3xl font-black tracking-tight text-slate-950 dark:text-white mb-1">
              Welcome back, {username.split(' ')[0]}
            </h1>
            <p className="text-slate-600 dark:text-slate-400 text-sm">
              Here is your financial and tax compliance overview. Everything is looking solid.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="px-4 py-2 bg-success/10 dark:bg-success/15 border border-success/20 dark:border-success/30 rounded-xl text-success flex items-center gap-2 text-sm font-semibold transition-colors">
              <CheckCircle2 className="h-4 w-4" />
              Audit Ready (92%)
            </div>
            <div className="px-4 py-2 bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl text-slate-700 dark:text-slate-300 flex items-center gap-2 text-sm font-semibold transition-colors">
              <Calendar className="h-4 w-4 text-secondary" />
              ITR-2 Filing Draft
            </div>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {/* Card 1 */}
          <div className="bg-white/60 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-850 p-6 rounded-2xl space-y-4 hover:border-primary/45 dark:hover:border-primary/45 hover:shadow-lg dark:hover:shadow-primary/5 transition-all duration-300 group hover:-translate-y-0.5">
            <div className="flex justify-between items-start">
              <span className="text-slate-500 dark:text-slate-400 text-xs font-bold uppercase tracking-wider">Financial Health Score</span>
              <div className="p-2 bg-primary/10 text-primary rounded-xl group-hover:scale-110 transition-transform">
                <TrendingUp className="h-5 w-5" />
              </div>
            </div>
            <div>
              <div className="text-3xl font-black text-slate-950 dark:text-white">92<span className="text-lg text-slate-400 dark:text-slate-500">/100</span></div>
              <div className="flex items-center gap-1.5 text-xs text-success mt-1">
                <ArrowUpRight className="h-3 w-3" />
                <span>+4% from last month</span>
              </div>
            </div>
          </div>

          {/* Card 2 */}
          <div className="bg-white/60 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-850 p-6 rounded-2xl space-y-4 hover:border-secondary/45 dark:hover:border-secondary/45 hover:shadow-lg dark:hover:shadow-secondary/5 transition-all duration-300 group hover:-translate-y-0.5">
            <div className="flex justify-between items-start">
              <span className="text-slate-500 dark:text-slate-400 text-xs font-bold uppercase tracking-wider">Total Tax Saved</span>
              <div className="p-2 bg-secondary/10 text-secondary rounded-xl group-hover:scale-110 transition-transform">
                <Percent className="h-5 w-5" />
              </div>
            </div>
            <div>
              <div className="text-3xl font-black text-slate-950 dark:text-white">₹1,45,200</div>
              <div className="flex items-center gap-1.5 text-xs text-success mt-1">
                <ArrowUpRight className="h-3 w-3" />
                <span>Optimized via Section 80C</span>
              </div>
            </div>
          </div>

          {/* Card 3 */}
          <div className="bg-white/60 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-850 p-6 rounded-2xl space-y-4 hover:border-success/45 dark:hover:border-success/45 hover:shadow-lg dark:hover:shadow-success/5 transition-all duration-300 group hover:-translate-y-0.5">
            <div className="flex justify-between items-start">
              <span className="text-slate-500 dark:text-slate-400 text-xs font-bold uppercase tracking-wider">Compliance Red Flags</span>
              <div className="p-2 bg-red-500/10 text-red-500 dark:text-red-400 rounded-xl group-hover:scale-110 transition-transform">
                <ShieldAlert className="h-5 w-5" />
              </div>
            </div>
            <div>
              <div className="text-3xl font-black text-slate-950 dark:text-white">0</div>
              <div className="flex items-center gap-1.5 text-xs text-success mt-1">
                <CheckCircle2 className="h-3.5 w-3.5" />
                <span>Fully compliant</span>
              </div>
            </div>
          </div>

          {/* Card 4 */}
          <div className="bg-white/60 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-850 p-6 rounded-2xl space-y-4 hover:border-slate-350 dark:hover:border-slate-800 hover:shadow-lg transition-all duration-300 group hover:-translate-y-0.5">
            <div className="flex justify-between items-start">
              <span className="text-slate-500 dark:text-slate-400 text-xs font-bold uppercase tracking-wider">Upcoming Deadline</span>
              <div className="p-2 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 rounded-xl group-hover:scale-110 transition-transform">
                <Calendar className="h-5 w-5" />
              </div>
            </div>
            <div>
              <div className="text-2xl font-black text-slate-900 dark:text-white">July 31, 2026</div>
              <div className="flex items-center gap-1.5 text-xs text-yellow-600 dark:text-yellow-500 mt-1">
                <AlertTriangle className="h-3.5 w-3.5" />
                <span>ITR filing due date</span>
              </div>
            </div>
          </div>
        </div>

        {/* Dynamic Analytics & Agent Modules */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Chart Widget */}
          <div className="lg:col-span-2 bg-white/60 dark:bg-slate-900/40 border border-slate-200 dark:border-slate-900 p-6 rounded-2xl flex flex-col space-y-4 transition-colors duration-300">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold text-slate-950 dark:text-white">Financial Health Score Trend</h3>
                <p className="text-slate-500 dark:text-slate-400 text-xs">A tracking score aggregated from tax efficiency and compliance factors</p>
              </div>
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-primary animate-pulse"></span>
                <span className="text-xs text-slate-500 dark:text-slate-400">Live Scorer Status</span>
              </div>
            </div>
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={healthData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorScore" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#1a5490" stopOpacity={0.4}/>
                      <stop offset="95%" stopColor="#1a5490" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="month" stroke="var(--chart-axis)" fontSize={11} tickLine={false} axisLine={false} />
                  <YAxis stroke="var(--chart-axis)" fontSize={11} domain={[50, 100]} tickLine={false} axisLine={false} />
                  <Tooltip 
                    contentStyle={{ backgroundColor: 'var(--tooltip-bg)', borderColor: 'var(--tooltip-border)', borderRadius: '12px' }}
                    labelStyle={{ color: 'var(--tooltip-text)', fontWeight: 'bold' }}
                    itemStyle={{ color: 'var(--tooltip-text)' }}
                  />
                  <Area type="monotone" dataKey="score" stroke="#1a5490" strokeWidth={2.5} fillOpacity={1} fill="url(#colorScore)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Action List & Agents */}
          <div className="bg-white/60 dark:bg-slate-900/40 border border-slate-200 dark:border-slate-900 p-6 rounded-2xl flex flex-col space-y-4 justify-between transition-colors duration-300">
            <div className="space-y-4">
              <div>
                <h3 className="text-lg font-bold text-slate-950 dark:text-white font-heading">AI Agents & Workspaces</h3>
                <p className="text-slate-500 dark:text-slate-400 text-xs">Run background jobs, check deductions, or file reports</p>
              </div>

              {/* Agent Grid */}
              <div className="space-y-3">
                {/* Agent 1 */}
                <div className="flex items-center justify-between p-3 bg-white dark:bg-slate-950/60 hover:bg-slate-50 dark:hover:bg-slate-900 border border-slate-200 dark:border-slate-900 rounded-xl transition-all cursor-pointer group">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-success/10 text-success rounded-lg">
                      <ShieldAlert className="h-4 w-4" />
                    </div>
                    <div>
                      <h4 className="text-sm font-semibold text-slate-900 dark:text-white group-hover:text-primary transition-colors">Compliance Checker</h4>
                      <p className="text-slate-500 dark:text-slate-400 text-xxs">Verify red flags & rules</p>
                    </div>
                  </div>
                  <ArrowUpRight className="h-4 w-4 text-slate-400 group-hover:text-primary transition-colors" />
                </div>

                {/* Agent 2 */}
                <div className="flex items-center justify-between p-3 bg-white dark:bg-slate-950/60 hover:bg-slate-50 dark:hover:bg-slate-900 border border-slate-200 dark:border-slate-900 rounded-xl transition-all cursor-pointer group">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-secondary/10 text-secondary rounded-lg">
                      <FileText className="h-4 w-4" />
                    </div>
                    <div>
                      <h4 className="text-sm font-semibold text-slate-900 dark:text-white group-hover:text-primary transition-colors">ITR Helper Agent</h4>
                      <p className="text-slate-500 dark:text-slate-400 text-xxs">Check eligibility & step-by-step filing</p>
                    </div>
                  </div>
                  <ArrowUpRight className="h-4 w-4 text-slate-400 group-hover:text-primary transition-colors" />
                </div>

                {/* Agent 3 */}
                <div className="flex items-center justify-between p-3 bg-white dark:bg-slate-950/60 hover:bg-slate-50 dark:hover:bg-slate-900 border border-slate-200 dark:border-slate-900 rounded-xl transition-all cursor-pointer group">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-primary/10 text-primary rounded-lg">
                      <Calculator className="h-4 w-4" />
                    </div>
                    <div>
                      <h4 className="text-sm font-semibold text-slate-900 dark:text-white group-hover:text-primary transition-colors">Advanced Calculator</h4>
                      <p className="text-slate-500 dark:text-slate-400 text-xxs">Multi-source income & capital gains</p>
                    </div>
                  </div>
                  <ArrowUpRight className="h-4 w-4 text-slate-400 group-hover:text-primary transition-colors" />
                </div>
              </div>
            </div>

            <button className="w-full mt-4 py-2.5 bg-gradient-to-r from-primary to-primary-dark hover:from-primary-dark hover:to-primary text-white font-bold text-sm rounded-xl transition-all duration-300 shadow-md shadow-primary/20 flex items-center justify-center gap-2 cursor-pointer">
              <Download className="h-4 w-4" />
              Generate Tax Report
            </button>
          </div>
        </div>

        {/* Quick Tips & Alerts */}
        <div className="bg-gradient-to-r from-primary/10 to-transparent p-6 rounded-2xl border border-primary/20 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="space-y-1">
            <span className="px-2 py-0.5 bg-primary/20 text-primary border border-primary/30 rounded text-xxs font-bold uppercase tracking-wider">Weekly Tip</span>
            <h4 className="text-sm font-bold text-slate-950 dark:text-white">Optimize Mutual Fund Gains before March 31</h4>
            <p className="text-slate-650 dark:text-slate-400 text-xs">
              You can harvest up to ₹1 Lakh in Long-Term Capital Gains (LTCG) tax-free every financial year under Section 112A.
            </p>
          </div>
          <button className="px-4 py-2 bg-white hover:bg-slate-100 dark:bg-slate-900 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-800 text-xs font-bold rounded-xl text-slate-700 dark:text-slate-200 whitespace-nowrap transition-all cursor-pointer">
            Learn More
          </button>
        </div>
      </main>
    </div>
  );
};

export default Dashboard;
