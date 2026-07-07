import React from 'react';
import Sidebar from './Sidebar';
import Topbar from './Topbar';
import CosmicBackground from '../common/CosmicBackground';
import { useUIStore } from '../../store/useUIStore';
import clsx from 'clsx';

interface AppLayoutProps {
  title?: string;
  subtitle?: string;
  children: React.ReactNode;
}

export default function AppLayout({ title, subtitle, children }: AppLayoutProps) {
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 relative overflow-hidden transition-colors duration-300">
      {/* Twinkling star constellations background */}
      <CosmicBackground mode="space" />

      {/* Dimmed backdrop overlay when sidebar is open on mobile */}
      {!collapsed && (
        <div
          onClick={toggleSidebar}
          className="fixed inset-0 z-40 bg-navy-deep/40 backdrop-blur-sm lg:hidden animate-fade-in"
        />
      )}

      <Sidebar />
      <div className={clsx('relative z-10 transition-all duration-305 ease-out', collapsed ? 'ml-0 lg:ml-[72px]' : 'ml-0 lg:ml-[248px]')}>
        <Topbar title={title} subtitle={subtitle} />
        <main className="p-6 max-w-[1400px] animate-page-enter relative z-10">
          {children}
        </main>
      </div>
    </div>
  );
}
