import { useState } from 'react';
import AppLayout from '../components/shared/AppLayout';
import { Card, SectionHeading, Badge } from '../components/ui/Primitives';
import { useApiData } from '../hooks/useApiData';
import { ErrorState, LoadingState } from '../components/shared/DataState';
import { getITRGuidance } from '../api/services';
import { Check, Clock, ExternalLink, XCircle, FileText } from 'lucide-react';
import clsx from 'clsx';

interface ITRStep {
  step: number;
  action: string;
  details: string;
  time_min: number;
}

export default function ITRGuide() {
  const state = useApiData<any>(getITRGuidance, []);
  const [completed, setCompleted] = useState<number[]>([]);

  if (state.loading) return <AppLayout title="ITR Guide"><LoadingState /></AppLayout>;
  if (state.error)
    return (
      <AppLayout title="ITR Guide">
        <ErrorState error={state.error} onRetry={state.refetch} what="your filing guidance" />
      </AppLayout>
    );
  const guide: any = state.data ?? {};
  const steps = (guide.step_by_step_guide ?? []) as ITRStep[];

  const toggle = (step: number) =>
    setCompleted((c) => (c.includes(step) ? c.filter((s) => s !== step) : [...c, step]));

  const totalTime = steps.reduce((a: number, s: ITRStep) => a + s.time_min, 0);

  return (
    <AppLayout title="ITR Filing Guide" subtitle="Step-by-step guidance tailored to your income profile">

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-6 stagger">
        <Card className="bg-gradient-to-br from-primary to-primary-dark text-white border-0 p-6">
          <p className="text-[11px] font-semibold tracking-wide uppercase text-white/70 mb-2">Recommended Form</p>
          <p className="font-display font-semibold text-[32px] mb-1">{guide.recommended_form}</p>
          <p className="text-[12.5px] text-white/70 mb-4">{guide.form_details?.applicable}</p>
          <Badge tone="neutral"><span className="text-white dark:text-slate-300">{guide.form_details?.complexity}</span></Badge>
        </Card>

        <Card className="p-6">
          <p className="text-[11px] font-semibold tracking-wide uppercase text-primary mb-2">Estimated time</p>
          <div className="flex items-center gap-2 mb-1">
            <Clock size={20} className="text-saffron" />
            <p className="ledger-num font-display font-semibold text-[28px] text-ink">{totalTime} min</p>
          </div>
          <p className="text-[12.5px] text-ink-soft">Across {steps.length} guided steps</p>
        </Card>

        <Card className="p-6">
          <p className="text-[11px] font-semibold tracking-wide uppercase text-primary mb-2">Deadline</p>
          <p className="ledger-num font-display font-semibold text-[28px] text-ink mb-1">{guide.days_to_deadline} days</p>
          <p className="text-[12.5px] text-ink-soft mb-3">left to file for FY {guide.financial_year}</p>
          <a href="https://www.incometax.gov.in" target="_blank" rel="noreferrer"
             className="inline-flex items-center gap-1.5 text-[12.5px] font-medium text-primary hover:gap-2 transition-all">
            Open e-filing portal <ExternalLink size={13} />
          </a>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 stagger">
        <Card className="lg:col-span-2 p-6">
          <SectionHeading
            eyebrow="Filing Checklist"
            title="Follow along, step by step"
            action={<span className="text-[12.5px] text-ink-soft ledger-num">{completed.length}/{steps.length} done</span>}
          />
          <div className="space-y-2 stagger">
            {steps.map((s: ITRStep) => {
              const done = completed.includes(s.step);
              return (
                <button
                  key={s.step}
                  onClick={() => toggle(s.step)}
                  className={clsx(
                    'w-full flex items-start gap-3 p-3.5 rounded-2xl border text-left transition-all cursor-pointer',
                    done ? 'bg-teal/5 border-teal/20 dark:bg-teal/10' : 'border-line hover:border-primary/30'
                  )}
                >
                  <div className={clsx(
                    'w-6 h-6 rounded-full flex items-center justify-center shrink-0 mt-0.5 text-[11px] font-semibold ledger-num transition-all duration-300',
                    done ? 'bg-teal text-white border-0' : 'bg-paper border border-line text-ink-soft'
                  )}>
                    {done ? <Check size={13} className="animate-spring-pop" /> : s.step}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className={clsx('text-[13.5px] font-medium leading-none mb-1', done ? 'text-ink-soft line-through' : 'text-ink')}>{s.action}</p>
                    <p className="text-[12px] text-ink-soft">{s.details}</p>
                  </div>
                  <span className="text-[11px] text-ink-soft ledger-num shrink-0">{s.time_min}m</span>
                </button>
              );
            })}
          </div>
        </Card>

        <Card className="p-6">
          <SectionHeading eyebrow="Avoid These" title="Common mistakes" />
          <div className="space-y-3">
            {(guide.common_mistakes ?? []).map((m: string, i: number) => (
              <div key={i} className="flex items-start gap-2.5">
                <XCircle size={15} className="text-danger shrink-0 mt-0.5" />
                <p className="text-[12.5px] text-ink-soft">{m}</p>
              </div>
            ))}
          </div>
          <div className="mt-5 pt-5 border-t border-line flex items-center gap-2.5">
            <FileText size={16} className="text-primary" />
            <p className="text-[12.2px] leading-relaxed text-ink-soft">Once filed, verify your ITR within 30 days — an unverified return is treated as not filed.</p>
          </div>
        </Card>
      </div>
    </AppLayout>
  );
}
