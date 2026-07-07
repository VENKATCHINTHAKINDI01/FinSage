import { useState } from 'react';
import AppLayout from '../components/shared/AppLayout';
import { Card, SectionHeading, Badge, DemoBadge, EmptyState } from '../components/ui/Primitives';
import { useApiData } from '../hooks/useApiData';
import { getReportsList, generateReport } from '../api/services';
import { mockReports } from '../utils/mockData';
import { formatDate } from '../utils/format';
import { FileStack, Download, ShieldCheck, Activity, Calculator, Loader2 } from 'lucide-react';

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
  const { data, isDemo } = useApiData(getReportsList, { reports: mockReports }, []);
  const reports = (data?.reports || mockReports) as ReportItem[];
  const [generating, setGenerating] = useState<string | null>(null);

  const handleGenerate = async (type: string) => {
    setGenerating(type);
    try {
      await generateReport(type);
    } catch (_) {
      // demo mode — no backend; simulate delay
      await new Promise((r) => setTimeout(r, 900));
    } finally {
      setGenerating(null);
    }
  };

  return (
    <AppLayout title="Reports" subtitle="Generate and download PDF reports of your financial position">
      <div className="flex justify-end mb-4"><DemoBadge show={isDemo} /></div>

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
                    <button className="justify-self-end flex items-center gap-1.5 text-[12.5px] font-medium text-primary hover:text-primary-dark cursor-pointer">
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
