import { useState } from 'react';
import { Menu, Search, Bell, X } from 'lucide-react';
import { useUIStore } from '../../store/useUIStore';
import { useAuthStore } from '../../store/useAuthStore';
import { Link } from 'react-router-dom';

interface TopbarProps {
  title?: string;
  subtitle?: string;
}

export default function Topbar({ title, subtitle }: TopbarProps) {
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const user = useAuthStore((s) => s.user) || { name: 'User', email: '' };
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const name = user.name || 'User';
  const initials = name.split(' ').map((n: string) => n[0]).slice(0, 2).join('').toUpperCase();

  const quickLinks = [
    { label: 'Dashboard', path: '/dashboard' },
    { label: 'Tax Analysis', path: '/tax-analysis' },
    { label: 'Smart Savings', path: '/smart-savings' },
    { label: 'Compliance', path: '/compliance' },
    { label: 'ITR Filing Guide', path: '/itr-guide' },
    { label: 'Health Score', path: '/health-score' },
    { label: 'Reports', path: '/reports' },
    { label: 'Profile', path: '/profile' },
  ];

  const filtered = searchQuery
    ? quickLinks.filter((l) => l.label.toLowerCase().includes(searchQuery.toLowerCase()))
    : quickLinks;

  return (
    <>
      {/* Search overlay */}
      {searchOpen && (
        <div
          className="fixed inset-0 z-50 bg-ink/40 backdrop-blur-sm flex items-start justify-center pt-24 px-4 animate-fade-in"
          onClick={() => { setSearchOpen(false); setSearchQuery(''); }}
        >
          <div
            className="w-full max-w-lg glass-galaxy rounded-2xl shadow-2xl overflow-hidden animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 p-4 border-b border-line">
              <Search size={18} className="text-ink-soft shrink-0" />
              <input
                autoFocus
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search pages, tools…"
                className="flex-1 bg-transparent text-[15px] text-ink placeholder:text-ink-soft outline-none"
              />
              <button
                onClick={() => { setSearchOpen(false); setSearchQuery(''); }}
                className="w-7 h-7 rounded-lg bg-line flex items-center justify-center text-ink-soft hover:text-ink transition-colors"
              >
                <X size={14} />
              </button>
            </div>
            <div className="p-2 max-h-72 overflow-y-auto">
              {filtered.map((l) => (
                <Link
                  key={l.path}
                  to={l.path}
                  onClick={() => { setSearchOpen(false); setSearchQuery(''); }}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13.5px] font-medium text-ink hover:bg-primary/8 transition-colors"
                >
                  <span className="w-5 h-5 rounded-md bg-primary/10 text-primary flex items-center justify-center text-[10px] font-bold shrink-0">→</span>
                  {l.label}
                </Link>
              ))}
            </div>
            <div className="px-4 py-2.5 border-t border-line flex items-center gap-2 text-[11px] text-ink-soft">
              <kbd className="px-1.5 py-0.5 rounded bg-line border border-line/50 font-mono">↵</kbd> to navigate
              <span className="mx-1">·</span>
              <kbd className="px-1.5 py-0.5 rounded bg-line border border-line/50 font-mono">Esc</kbd> to close
            </div>
          </div>
        </div>
      )}

      <header className="sticky top-0 z-30 h-16 bg-white/40 dark:bg-slate-950/40 backdrop-blur-md border-b border-line dark:border-white/5 flex items-center gap-4 px-6">
        {/* Sidebar toggle */}
        <button
          onClick={toggleSidebar}
          className="w-9 h-9 rounded-xl flex items-center justify-center text-ink-soft hover:bg-white/80 dark:hover:bg-slate-800/50 hover:shadow-md transition-all cursor-pointer"
          aria-label="Toggle sidebar"
        >
          <Menu size={18} />
        </button>

        {/* Title */}
        <div className="min-w-0 flex-1">
          <h1 className="font-display font-bold text-[17px] leading-tight text-ink truncate">{title}</h1>
          {subtitle && <p className="text-[11.5px] text-ink-soft truncate">{subtitle}</p>}
        </div>

        {/* Search trigger */}
        <button
          onClick={() => setSearchOpen(true)}
          className="hidden md:flex items-center gap-2 h-9 px-3 rounded-xl bg-white/70 dark:bg-slate-900/60 border border-line dark:border-white/10 text-ink-soft text-[13px] hover:border-primary/40 hover:shadow-sm transition-all w-52 group"
        >
          <Search size={14} className="group-hover:text-primary transition-colors" />
          <span className="flex-1 text-left">Search…</span>
          <kbd className="text-[10px] px-1.5 py-0.5 rounded-md bg-paper border border-line font-mono">⌘K</kbd>
        </button>

        {/* Notification bell — was a dead button (no onClick) with an
            unconditional "unread" dot shown regardless of whether there
            was any actual unread activity. Now links to the real
            notifications page; the dot is gone rather than faked, since
            this component has no real unread-count data to back it. */}
        <Link
          to="/settings"
          className="relative w-9 h-9 rounded-xl flex items-center justify-center text-ink-soft hover:bg-white/80 dark:hover:bg-slate-800/50 hover:shadow-md transition-all cursor-pointer group"
          aria-label="Notifications"
        >
          <Bell size={18} className="group-hover:text-primary transition-colors" />
        </Link>

        {/* User avatar */}
        <Link
          to="/profile"
          className="flex items-center gap-2.5 pl-1 pr-3 h-9 rounded-xl hover:bg-white/80 dark:hover:bg-slate-800/50 hover:shadow-md transition-all cursor-pointer group"
        >
          <div className="relative">
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-primary to-teal text-white text-[11px] font-bold flex items-center justify-center shrink-0">
              {initials}
            </div>
            <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-teal border-2 border-white" />
          </div>
          <span className="hidden sm:block text-[13px] font-semibold text-ink group-hover:text-primary transition-colors">
            {name.split(' ')[0]}
          </span>
        </Link>
      </header>
    </>
  );
}
