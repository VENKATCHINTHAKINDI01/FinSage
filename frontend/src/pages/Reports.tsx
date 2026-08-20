import { useState } from 'react';
import AppLayout from '../components/shared/AppLayout';
import { Card, SectionHeading, Badge, EmptyState } from '../components/ui/Primitives';
import { useApiData } from '../hooks/useApiData';
import { ErrorState, LoadingState } from '../components/shared/DataState';
import { getReportsList, generateReport } from '../api/services';
import { formatDate } from '../utils/format';
import { FileStack, Download, ShieldCheck, Activity, Calculator, Loader2, AlertTriangle } from 'lucide-react';

const REPORT_TYPES = [
  { type: 'compliance', label: 'Compliance Report', desc: 'Audit readiness, red flags, and recommendations', icon: ShieldCheck, accent: 'primary' },
  { type: 'financial_health', label: 'Financial Health Report', desc: '5-factor score breakdown and trends', icon: Activity, accent: 'teal' },
  { type: 'tax_summary', label: 'Tax Summary Report', desc: 'Income, deductions, and liability overview', icon: Calculator, accent: 'saffron' },
];

const typeIcon: Record<string, typeof ShieldCheck> = { 
  compliance: ShieldCheck, 
  financial_health: Activity, 
  tax_summary: Calculator 
};

function bytesToSize(bytes: number): string {
  if (!bytes) return '—';
  const kb = bytes / 1024;
  return kb > 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${kb.toFixed(0)} KB`;
}

interface ReportItem {
  id: string;
  title: string;
  type: string;
  generated: string;
  size: number;
}

export default function Reports() {
  const state = useApiData<any>(getReportsList, []);
  const [generating, setGenerating] = useState<string | null>(null);
  const [genError, setGenError] = useState<string | null>(null);

  const handleGenerate = async (type: string) => {
    setGenerating(type);
    setGenError(null);
    try {
      const res = await generateReport(type);
      // The API returns HTTP 200 even when generation failed server-side
      // (e.g. "boto3 is not installed, so the document vault is
      // unavailable") — api/client.ts only throws on a non-2xx status, so
      // a failed generation looks exactly like a successful one unless the
      // body's own success flag is checked here too.
      if (res?.success === false) {
        throw new Error('Report generation failed on the server. Please try again later.');
      }
      state.refetch();
    } catch (err) {
      // Was silently swallowed here and treated as success ("demo mode — no
      // backend; simulate delay") — a real failure (e.g. the document vault
      // being unavailable) looked identical to a completed report. No
      // fabricated success state now: a real error surfaces as one.
      setGenError(err instanceof Error ? err.message : 'Could not generate this report. Please try again.');
    } finally {
      setGenerating(null);
    }
  };

  if (state.loading) return <AppLayout title="Reports"><LoadingState /></AppLayout>;
  if (state.error)
    return (
      <AppLayout title="Reports">
        <ErrorState error={state.error} onRetry={state.refetch} what="your reports" />
      </AppLayout>
    );
  const reports = ((state.data as any)?.reports ?? []) as ReportItem[];

  return (
    <AppLayout title="Reports" subtitle="Generate and download PDF reports of your financial position">

      {genError && (
        <div className="flex items-start gap-3 p-4 mb-5 rounded-xl bg-danger/10 border border-danger/25">
          <AlertTriangle size={16} className="text-danger mt-0.5 shrink-0" />
          <p className="text-[13px] text-ink">{genError}</p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-6 stagger">
        {REPORT_TYPES.map(({ type, label, desc, icon: Icon, accent }) => (
          <Card key={type} className="flex flex-col p-6">
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center mb-4 shrink-0 ${
              accent === 'primary' 
                ? 'bg-primary/10 text-primary' 
                : accent === 'teal' 
                  ? 'bg-teal/10 text-teal' 
                  : 'bg-saffron/10 text-saffron'
            }`}>
              <Icon size={18} />
            </div>
            <p className="font-display font-semibold text-[15px] text-ink mb-1">{label}</p>
            <p className="text-[12.5px] text-ink-soft mb-5 flex-1">{desc}</p>
            <button
              onClick={() => handleGenerate(type)}
              disabled={generating === type}
              className="w-full h-9 rounded-lg bg-primary hover:bg-primary-dark text-white text-[13px] font-medium flex items-center justify-center gap-2 transition-colors disabled:opacity-60 cursor-pointer"
            >
              {generating === type ? <Loader2 size={14} className="animate-spin" /> : <FileStack size={14} />}
              {generating === type ? 'Generating…' : 'Generate PDF'}
            </button>
          </Card>
        ))}
      </div>

      <Card className="p-6">
        <SectionHeading eyebrow="History" title="Your reports" action={<Badge tone="neutral">{reports.length} total</Badge>} />
        {reports.length ? (
          <div>
            <div className="grid grid-cols-[1fr_auto_auto_auto] gap-4 pb-2 mb-2 border-b border-line text-[11px] font-semibold text-ink-soft uppercase tracking-wide">
              <span>Report</span><span>Generated</span><span>Size</span><span className="text-right">Action</span>
            </div>
            <div className="space-y-0 stagger">
              {reports.map((r: ReportItem) => {
                const Icon = typeIcon[r.type] || FileStack;
                return (
                  <div key={r.id} className="grid grid-cols-[1fr_auto_auto_auto] gap-4 items-center py-3 border-b border-line last:border-0">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0"><Icon size={15} /></div>
                      <span className="text-[13.5px] font-medium text-ink truncate">{r.title}</span>
                    </div>
                    <span className="text-[12.5px] text-ink-soft ledger-num whitespace-nowrap">{formatDate(r.generated)}</span>
                    <span className="text-[12.5px] text-ink-soft ledger-num whitespace-nowrap">{bytesToSize(r.size)}</span>
                    {/* No download route exists on the backend yet (report_generator.py
                        constructs a file_url pointing at /api/v1/reports/download/{id},
                        but that route was never registered) — disabled rather than a
                        button that looks live and 404s or does nothing on click. */}
                    <button
                      disabled
                      title="Downloads aren't available yet"
                      className="justify-self-end flex items-center gap-1.5 text-[12.5px] font-medium text-ink-soft opacity-50 cursor-not-allowed"
                    >
                      <Download size={14} /> Download
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <EmptyState icon={FileStack} title="No reports yet" message="Generate your first report using the cards above." />
        )}
      </Card>
    </AppLayout>
  );
}
