import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, Calculator, ShieldCheck, FileStack,
  Activity, FileSignature, Bell, UserCircle, IndianRupee, Zap, Landmark,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useUIStore } from '../../store/useUIStore';
import { useProfileStore, TAX_YEAR, ITR_DEADLINE, ITR_DEADLINE_ISO } from '../../store/useProfileStore';
import clsx from 'clsx';

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
  badge?: string;
}

const NAV: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/tax-analysis', label: 'Tax Analysis', icon: Calculator },
  { to: '/smart-savings', label: 'Smart Savings', icon: Zap, badge: 'AI' },
  { to: '/benefits', label: 'Benefits & Schemes', icon: Landmark, badge: 'AI' },
  { to: '/compliance', label: 'Compliance', icon: ShieldCheck },
  { to: '/itr-guide', label: 'ITR Filing Guide', icon: FileSignature },
  { to: '/health-score', label: 'Health Score', icon: Activity },
  { to: '/reports', label: 'Reports', icon: FileStack },
  { to: '/settings', label: 'Notifications', icon: Bell },
  { to: '/profile', label: 'Profile', icon: UserCircle },
];

export default function Sidebar() {
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  const { completeness } = useProfileStore();

  // Days to the ITR deadline. Was hardcoded to 2026-07-31 — a date already
  // in the past by the time this ships for FY 2026-27 — which silently
  // clamped to "0d left" via the Math.max(0, ...) below rather than
  // reflecting the actual next deadline. Sourced from ITR_DEADLINE_ISO so
  // the two never drift apart again.
  const daysLeft = Math.max(0, Math.ceil(
    (new Date(ITR_DEADLINE_ISO).getTime() - Date.now()) / 86400000
  ));
  const deadlinePct = Math.min(100, Math.max(0, 100 - (daysLeft / 120) * 100));

  return (
    <aside
      className={clsx(
        'fixed left-0 top-0 h-screen flex flex-col z-50 transition-all duration-305 ease-out',
        'bg-gradient-to-b from-navy to-navy-deep border-r border-white/5 shadow-2xl lg:shadow-none',
        collapsed ? '-translate-x-full lg:translate-x-0 lg:w-[72px]' : 'translate-x-0 w-[248px]'
      )}
    >
      {/* Subtle grid overlay */}
      <div className="absolute inset-0 opacity-[0.03] pointer-events-none"
        style={{ backgroundImage: 'radial-gradient(circle at 1px 1px, white 1px, transparent 0)', backgroundSize: '24px 24px' }}
      />

      {/* Logo */}
      <div className="relative flex items-center gap-3 px-4 h-16 border-b border-white/10 shrink-0">
        <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-saffron via-primary to-teal flex items-center justify-center shrink-0 shadow-lg animate-gradient"
          style={{ backgroundSize: '200% 200%' }}>
          <IndianRupee size={17} strokeWidth={2.5} className="text-white" />
        </div>
        {!collapsed && (
          <div className="leading-tight overflow-hidden">
            <p className="font-display font-bold text-[15px] tracking-tight whitespace-nowrap text-white">FinSage AI</p>
            <p className="text-[10px] text-white/40 tracking-wide whitespace-nowrap">{TAX_YEAR} · India</p>
          </div>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto">
        {NAV.map(({ to, label, icon: Icon, end, badge }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            title={collapsed ? label : undefined}
            className={({ isActive }) =>
              clsx(
                'relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-medium transition-all duration-150 group',
                isActive
                  ? 'nav-item-active'
                  : 'text-white/55 hover:text-white hover:bg-white/6'
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon size={17} strokeWidth={isActive ? 2.5 : 2} className="shrink-0" />
                {!collapsed && (
                  <span className="whitespace-nowrap flex-1">{label}</span>
                )}
                {!collapsed && badge && (
                  <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-md bg-saffron/20 text-saffron-light tracking-wide">
                    {badge}
                  </span>
                )}
                {/* Tooltip for collapsed state */}
                {collapsed && (
                  <div className="absolute left-full ml-3 px-2.5 py-1.5 rounded-lg bg-navy-deep text-white text-[12px] font-medium whitespace-nowrap shadow-xl opacity-0 group-hover:opacity-100 transition-opacity duration-150 pointer-events-none z-50 border border-white/10">
                    {label}
                    {badge && <span className="ml-1.5 text-saffron-light text-[9px]">AI</span>}
                  </div>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Profile completeness */}
      {!collapsed && completeness < 100 && (
        <div className="mx-3 mb-2 p-3 rounded-xl bg-white/5 border border-white/8">
          <div className="flex justify-between items-center mb-1.5">
            <p className="text-[10.5px] text-white/50">Profile strength</p>
            <p className="text-[10.5px] font-bold text-white/70 ledger-num">{completeness}%</p>
          </div>
          <div className="h-1 rounded-full bg-white/10 overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-saffron to-teal transition-all duration-700"
              style={{ width: `${completeness}%` }}
            />
          </div>
        </div>
      )}

      {/* ITR deadline */}
      {!collapsed && (
        <div className="p-3 mx-3 mb-4 rounded-xl bg-white/5 border border-white/8">
          <div className="flex justify-between items-center mb-1">
            <p className="text-[10.5px] text-white/40">ITR Deadline</p>
            <span className={clsx(
              'text-[9.5px] font-bold px-1.5 py-0.5 rounded-md',
              daysLeft <= 30 ? 'bg-danger/20 text-red-300' : daysLeft <= 60 ? 'bg-saffron/20 text-saffron-light' : 'bg-teal/15 text-teal-light'
            )}>
              {daysLeft}d left
            </span>
          </div>
          <p className="text-[13px] font-bold ledger-num text-white mb-2">{ITR_DEADLINE}</p>
          <div className="h-1 rounded-full bg-white/10 overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-teal to-saffron"
              style={{ width: `${deadlinePct}%` }}
            />
          </div>
        </div>
      )}
    </aside>
  );
}
