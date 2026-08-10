import clsx from 'clsx';
import React from 'react';
import type { LucideIcon } from 'lucide-react';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children?: React.ReactNode;
}

export function Card({ children, className, ...props }: CardProps) {
  return (
    <div className={clsx('card p-5', className)} {...props}>
      {children}
    </div>
  );
}

interface SectionHeadingProps {
  eyebrow?: string;
  title: string;
  action?: React.ReactNode;
}

export function SectionHeading({ eyebrow, title, action }: SectionHeadingProps) {
  return (
    <div className="flex items-end justify-between mb-4">
      <div>
        {eyebrow && <p className="text-[11px] font-semibold tracking-wide uppercase text-primary-500 mb-1">{eyebrow}</p>}
        <h2 className="font-display font-semibold text-[18px] text-ink">{title}</h2>
      </div>
      {action}
    </div>
  );
}

const badgeColors = {
  low: 'bg-teal-soft text-teal border-teal/20',
  medium: 'bg-saffron-soft text-saffron border-saffron/20',
  high: 'bg-red-50 text-danger border-danger/20',
  neutral: 'bg-primary-50 text-primary-600 border-primary-100',
};

interface BadgeProps {
  tone?: 'low' | 'medium' | 'high' | 'neutral';
  children: React.ReactNode;
}

export function Badge({ tone = 'neutral', children }: BadgeProps) {
  return (
    <span className={clsx('inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11.5px] font-medium border', badgeColors[tone])}>
      {children}
    </span>
  );
}

interface ProgressBarProps {
  value: number;
  max?: number;
  tone?: 'primary' | 'saffron' | 'teal' | 'danger';
}

export function ProgressBar({ value, max = 100, tone = 'primary' }: ProgressBarProps) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  const colors = {
    primary: 'bg-primary-500',
    saffron: 'bg-saffron',
    teal: 'bg-teal',
    danger: 'bg-danger',
  };
  return (
    <div className="h-1.5 w-full rounded-full bg-line overflow-hidden">
      <div className={clsx('h-full rounded-full transition-all duration-700', colors[tone])} style={{ width: `${pct}%` }} />
    </div>
  );
}

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  message: string;
  action?: React.ReactNode;
}

export function EmptyState({ icon: Icon, title, message, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-14 px-6">
      {Icon && (
        <div className="w-12 h-12 rounded-xl bg-primary-50 text-primary-500 flex items-center justify-center mb-4">
          <Icon size={22} />
        </div>
      )}
      <p className="font-display font-semibold text-ink text-[15px] mb-1">{title}</p>
      <p className="text-ink-soft text-[13px] max-w-sm mb-4">{message}</p>
      {action}
    </div>
  );
}
