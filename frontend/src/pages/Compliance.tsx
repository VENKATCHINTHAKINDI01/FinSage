import AppLayout from '../components/shared/AppLayout';
import { Card, SectionHeading, Badge, ProgressBar, EmptyState } from '../components/ui/Primitives';
import ScoreGauge from '../components/ui/ScoreGauge';
import { useApiData } from '../hooks/useApiData';
import { ErrorState, LoadingState } from '../components/shared/DataState';
import { getComplianceReport } from '../api/services';
import { AlertTriangle, FileWarning, ShieldCheck, CheckCircle2 } from 'lucide-react';

const severityTone: Record<'High' | 'Medium' | 'Low', 'high' | 'medium' | 'low'> = { 
  High: 'high', 
  Medium: 'medium', 
  Low: 'low' 
};

interface RedFlag {
  flag: string;
  severity: 'High' | 'Medium' | 'Low';
  action: string;
}

export default function Compliance() {
  const state = useApiData<any>(getComplianceReport, []);
  if (state.loading) return <AppLayout title="Compliance"><LoadingState /></AppLayout>;
  if (state.error)
    return (
      <AppLayout title="Compliance">
        <ErrorState error={state.error} onRetry={state.refetch} what="your compliance report" />
      </AppLayout>
    );
  const c: any = state.data ?? {};

  return (
    <AppLayout title="Compliance" subtitle="Audit readiness, red flags, and documentation status">

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-6 stagger">
        <Card className="flex flex-col items-center text-center p-6">
          <p className="text-[11px] font-semibold tracking-wide uppercase text-primary mb-3">Compliance Score</p>
          <ScoreGauge score={c.compliance_score} />
          <div className="mt-4">
            <Badge tone={c.audit_ready ? 'low' : 'medium'}>
              {c.audit_ready ? <CheckCircle2 size={13} className="mr-1 inline" /> : <AlertTriangle size={13} className="mr-1 inline" />}
              {c.audit_readiness_status}
            </Badge>
          </div>
        </Card>

        <Card className="lg:col-span-2 p-6">
          <SectionHeading eyebrow="Risk Assessment" title="Where you stand with the IT Department" />
          <div className="rounded-2xl bg-paper border border-line p-4 mb-4">
            <p className="text-[13.5px] font-medium text-ink">{c.risk_level}</p>
            <p className="text-[12px] text-ink-soft mt-1">Based on {c.red_flags?.length || 0} flag(s) detected against income, TDS, and GST patterns typical of IT Department scrutiny.</p>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="rounded-2xl border border-line p-4">
              <p className="text-[11px] text-ink-soft mb-1">ITR filing deadline</p>
              <p className="ledger-num text-[15px] font-semibold text-ink">{c.itr_deadline}</p>
            </div>
            <div className="rounded-2xl border border-line p-4">
              <p className="text-[11px] text-ink-soft mb-1">Days remaining</p>
              <p className="ledger-num text-[15px] font-semibold text-saffron">{c.days_to_deadline} days</p>
            </div>
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 stagger">
        <Card className="p-6">
          <SectionHeading eyebrow="Detected Issues" title="Red flags" action={<Badge tone="medium">{c.red_flags?.length || 0} found</Badge>} />
          {c.red_flags?.length ? (
            <div className="space-y-3">
              {c.red_flags.map((f: RedFlag, i: number) => (
                <div key={i} className="flex items-start gap-3 p-3 rounded-2xl border border-line">
                  <div className="w-8 h-8 rounded-lg bg-saffron/10 text-saffron flex items-center justify-center shrink-0">
                    <AlertTriangle size={15} />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <p className="text-[13px] font-medium text-ink leading-none">{f.flag}</p>
                      <Badge tone={severityTone[f.severity] || 'neutral'}>{f.severity}</Badge>
                    </div>
                    <p className="text-[12px] text-ink-soft">{f.action}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState icon={ShieldCheck} title="No red flags detected" message="Your filing profile currently shows no known risk patterns." />
          )}
        </Card>

        <Card className="p-6">
          <SectionHeading eyebrow="Documentation" title="Missing documents" action={<Badge tone="neutral">{c.missing_documents?.length || 0} pending</Badge>} />
          {c.missing_documents?.length ? (
            <div className="space-y-2.5">
              {c.missing_documents.map((doc: string, i: number) => (
                <div key={i} className="flex items-center gap-3 py-2.5 border-b border-line last:border-0">
                  <FileWarning size={16} className="text-primary shrink-0" />
                  <span className="text-[13px] text-ink">{doc}</span>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState icon={CheckCircle2} title="All documents in order" message="Nothing outstanding for this assessment." />
          )}

          <div className="mt-5 pt-5 border-t border-line">
            <p className="text-[11px] font-semibold tracking-wide uppercase text-ink-soft mb-2">Document completeness</p>
            <ProgressBar value={100 - (c.missing_documents?.length || 0) * 12} tone="teal" />
          </div>
        </Card>
      </div>

      <Card className="mt-5 p-6">
        <SectionHeading eyebrow="Recommended Actions" title="What to do next" />
        <div className="space-y-2.5">
          {(c.recommendations || []).map((r: string, i: number) => (
            <div key={i} className="flex items-center gap-3 py-2.5 border-b border-line last:border-0">
              <span className="ledger-num text-[11px] font-semibold text-primary bg-primary/10 w-6 h-6 rounded-md flex items-center justify-center shrink-0">{i + 1}</span>
              <span className="text-[13.5px] text-ink">{r}</span>
            </div>
          ))}
        </div>
      </Card>
    </AppLayout>
  );
}
