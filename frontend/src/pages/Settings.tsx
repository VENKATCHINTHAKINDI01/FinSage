import { useState } from 'react';
import AppLayout from '../components/shared/AppLayout';
import { Card, SectionHeading, Badge, EmptyState } from '../components/ui/Primitives';
import { useApiData } from '../hooks/useApiData';
import { ErrorState, LoadingState } from '../components/shared/DataState';
import { getNotificationPreferences, setNotificationPreferences, getNotificationHistory } from '../api/services';
import { Mail, Send, Bell, Check, AlertTriangle } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import clsx from 'clsx';

const FREQUENCIES = ['daily', 'weekly', 'monthly', 'as_needed'];
const FREQ_LABEL: Record<string, string> = { 
  daily: 'Daily', 
  weekly: 'Weekly', 
  monthly: 'Monthly', 
  as_needed: 'As needed' 
};

interface ToggleProps {
  checked: boolean;
  onChange: (val: boolean) => void;
}

function Toggle({ checked, onChange }: ToggleProps) {
  return (
    <button
      onClick={() => onChange(!checked)}
      className={clsx('w-10 h-6 rounded-full flex items-center px-0.5 transition-colors cursor-pointer', checked ? 'bg-primary justify-end' : 'bg-line justify-start')}
      aria-pressed={checked}
    >
      <span className="w-5 h-5 rounded-full bg-white shadow" />
    </button>
  );
}

interface ChannelCardProps {
  channelKey: string;
  icon: LucideIcon;
  title: string;
  description: string;
  initial: { enabled?: boolean; frequency?: string };
}

function ChannelCard({ channelKey, icon: Icon, title, description, initial }: ChannelCardProps) {
  const [enabled, setEnabled] = useState(initial?.enabled ?? false);
  const [frequency, setFrequency] = useState(initial?.frequency || 'weekly');
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState(false);

  const save = async () => {
    setSaveError(false);
    try {
      await setNotificationPreferences({ channel: channelKey, enabled, frequency });
      setSaved(true);
      setTimeout(() => setSaved(false), 1800);
    } catch {
      // Was swallowed here ("demo mode") and unconditionally showed "Saved"
      // regardless of whether the preference was actually persisted.
      setSaveError(true);
      setTimeout(() => setSaveError(false), 2500);
    }
  };

  return (
    <Card className="p-6">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0"><Icon size={18} /></div>
          <div>
            <p className="font-display font-semibold text-[15px] text-ink leading-tight">{title}</p>
            <p className="text-[12px] text-ink-soft mt-0.5">{description}</p>
          </div>
        </div>
        <Toggle checked={enabled} onChange={setEnabled} />
      </div>

      {enabled && (
        <div className="pt-4 border-t border-line">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft mb-2">Frequency</p>
          <div className="flex flex-wrap gap-2 mb-4">
            {FREQUENCIES.map((f) => (
              <button
                key={f}
                onClick={() => setFrequency(f)}
                className={clsx(
                  'px-3 py-1.5 rounded-lg text-[12.5px] font-medium border transition-colors cursor-pointer',
                  frequency === f ? 'bg-primary text-white border-primary' : 'border-line text-ink-soft hover:border-primary/30'
                )}
              >
                {FREQ_LABEL[f]}
              </button>
            ))}
          </div>
        </div>
      )}

      <button
        onClick={save}
        className={clsx(
          'w-full h-9 rounded-lg text-white text-[13px] font-medium flex items-center justify-center gap-2 transition-colors cursor-pointer',
          saveError ? 'bg-danger hover:bg-danger' : 'bg-primary hover:bg-primary-dark'
        )}
      >
        {saved ? <><Check size={14} /> Saved</> : saveError ? <><AlertTriangle size={14} /> Couldn't save — try again</> : 'Save preference'}
      </button>
    </Card>
  );
}

interface NotificationItem {
  subject?: string;
  type: string;
  sent_at?: string;
}

export default function Settings() {
  const state = useApiData<any>(getNotificationPreferences, []);
  const { data: history } = useApiData<any>(getNotificationHistory, []);

  if (state.loading) return <AppLayout title="Settings"><LoadingState /></AppLayout>;
  if (state.error)
    return (
      <AppLayout title="Settings">
        <ErrorState error={state.error} onRetry={state.refetch} what="your notification preferences" />
      </AppLayout>
    );
  const p: any = (state.data as any)?.preferences ?? {};
  const notifications = (history?.notifications || []) as NotificationItem[];

  return (
    <AppLayout title="Notifications" subtitle="Choose how and when FinSage AI reaches you">

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mb-6 stagger">
        <ChannelCard channelKey="email" icon={Mail} title="Email" description="Weekly tips, deadline reminders, reports" initial={p.email} />
        <ChannelCard channelKey="telegram" icon={Send} title="Telegram" description="Real-time alerts via bot" initial={p.telegram} />
      </div>

      <Card className="p-6">
        <SectionHeading eyebrow="Recent Activity" title="Notification history" action={<Badge tone="neutral">{notifications.length + ' sent'}</Badge>} />
        {notifications.length ? (
          <div className="space-y-2.5 stagger">
            {notifications.map((n, i) => (
              <div key={i} className="flex items-center gap-3 py-2.5 border-b border-line last:border-0">
                <Bell size={15} className="text-primary shrink-0" />
                <span className="text-[13px] text-ink flex-1">{n.subject || n.type}</span>
                <span className="text-[11.5px] text-ink-soft ledger-num">{n.sent_at ? new Date(n.sent_at).toLocaleDateString('en-IN') : '—'}</span>
              </div>
            ))}
          </div>
        ) : (
          // Was 5 hardcoded fake notifications with fabricated "1w ago"-style
          // timestamps, shown as if they were real history — and the badge
          // above showed "5 sent" (`notifications.length || 5`) even with
          // zero real notifications.
          <EmptyState icon={Bell} title="No notifications yet" message="Activity will appear here once FinSage AI sends you a reminder, tip, or report." />
        )}
      </Card>
    </AppLayout>
  );
}
