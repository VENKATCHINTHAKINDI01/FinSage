import type { LucideIcon } from 'lucide-react';

interface StatCardProps {
  label: string;
  value: string | number;
  icon: LucideIcon;
  accent?: 'primary' | 'saffron' | 'teal';
  delta?: number;
  deltaLabel?: string;
}

const accentMap = {
  primary: { icon: 'text-primary bg-primary/10', bar: 'bg-primary', glow: 'rgba(26,84,144,0.12)' },
  saffron: { icon: 'text-saffron bg-saffron/10', bar: 'bg-saffron', glow: 'rgba(217,119,6,0.12)' },
  teal:    { icon: 'text-teal bg-teal/10',       bar: 'bg-teal',    glow: 'rgba(13,148,136,0.12)' },
};

export default function StatCard({ label, value, icon: Icon, accent = 'primary', delta, deltaLabel }: StatCardProps) {
  const ac = accentMap[accent];
  const isPositive = delta !== undefined && delta > 0;

  return (
    <div className="card p-5 relative overflow-hidden group cursor-default">
      {/* Top accent bar */}
      <div className={`absolute top-0 left-0 right-0 h-[3px] ${ac.bar} opacity-70`} />

      {/* Glow on hover */}
      <div
        className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none rounded-2xl"
        style={{ background: `radial-gradient(circle at 30% 40%, ${ac.glow}, transparent 70%)` }}
      />

      <div className="flex items-start justify-between relative">
        <div className="space-y-1.5">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-soft">{label}</p>
          <p className="ledger-num font-display font-bold text-[24px] leading-none text-ink">{value}</p>
          {delta !== undefined && (
            <div className="flex items-center gap-1 text-[11.5px] pt-0.5">
              <span className={`font-bold ${isPositive ? 'text-teal' : 'text-danger'}`}>
                {isPositive ? '▲ +' : '▼ '}{delta}
              </span>
              <span className="text-ink-soft">{deltaLabel}</span>
            </div>
          )}
        </div>
        <div className={`p-2.5 rounded-xl shrink-0 ${ac.icon} transition-transform group-hover:scale-110 duration-200`}>
          <Icon size={20} strokeWidth={2} />
        </div>
      </div>
    </div>
  );
}
