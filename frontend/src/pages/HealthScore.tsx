import AppLayout from '../components/shared/AppLayout';
import { Card, SectionHeading, ProgressBar, Badge } from '../components/ui/Primitives';
import ScoreGauge from '../components/ui/ScoreGauge';
import { FactorRadar } from '../components/shared/Charts';
import { useApiData } from '../hooks/useApiData';
import { EmptyState, ErrorState, LoadingState } from '../components/shared/DataState';
import { getHealthScore } from '../api/services';
import { Lightbulb } from 'lucide-react';

const FACTOR_LABELS: Record<string, string> = {
  tax_efficiency: 'Tax Efficiency',
  deduction_optimization: 'Deduction Optimization',
  savings_potential: 'Savings Potential',
  compliance_status: 'Compliance Status',
  investment_diversity: 'Investment Diversity',
};

const toneFor = (score: number): 'teal' | 'saffron' | 'danger' => 
  (score >= 80 ? 'teal' : score >= 60 ? 'saffron' : 'danger');

interface BreakdownItem {
  score: number;
  description: string;
}

export default function HealthScore() {
  const state = useApiData<any>(getHealthScore, []);
  if (state.loading) return <AppLayout title="Financial Health"><LoadingState /></AppLayout>;
  if (state.error)
    return (
      <AppLayout title="Financial Health">
        <ErrorState error={state.error} onRetry={state.refetch} what="your health score" />
      </AppLayout>
    );
  const h: any = (state.data as any)?.result ?? {};

  const breakdown = (h.breakdown ?? {}) as Record<string, BreakdownItem>;

  const radarData = Object.entries(breakdown).map(([key, v]) => ({
    factor: (FACTOR_LABELS[key] || key).split(' ')[0],
    score: v.score,
  }));

  return (
    <AppLayout title="Financial Health Score" subtitle="Five weighted factors, recalculated monthly">

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-6 stagger">
        <Card className="flex flex-col items-center justify-center text-center p-6">
          <ScoreGauge score={h.overall_score} size={190} />
          <p className="text-[12.5px] text-ink-soft mt-3 max-w-[220px]">{h.health_status?.message}</p>
          <div className="mt-3">
            <Badge tone="medium">{h.trend?.status}</Badge>
          </div>
        </Card>

        <Card className="lg:col-span-2 p-6">
          <SectionHeading eyebrow="Six Months" title="Trend" />
          <EmptyState title="No trend data yet" hint="Your score is tracked monthly; the trend appears after your second score." />
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5 mb-6 stagger">
        <Card className="lg:col-span-2 p-6">
          <SectionHeading eyebrow="Shape" title="Factor Radar" />
          <FactorRadar data={radarData} />
        </Card>

        <Card className="lg:col-span-3 p-6">
          <SectionHeading eyebrow="20% weight each" title="Factor breakdown" />
          <div className="space-y-5">
            {Object.entries(breakdown).map(([key, v]) => (
              <div key={key}>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[13.5px] font-medium text-ink">{FACTOR_LABELS[key] || key}</span>
                  <span className="ledger-num text-[13px] font-semibold text-ink">{v.score}/100</span>
                </div>
                <ProgressBar value={v.score} tone={toneFor(v.score)} />
                <p className="text-[11.5px] text-ink-soft mt-1.5">{v.description}</p>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card className="p-6">
        <SectionHeading eyebrow="Personalized" title="Recommendations to raise your score" action={<Lightbulb size={18} className="text-saffron" />} />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 stagger">
          {(h.recommendations ?? []).map((r: string, i: number) => (
            <div key={i} className="p-4 rounded-2xl border border-line bg-paper">
              <p className="text-[13px] text-ink leading-relaxed">{r}</p>
            </div>
          ))}
        </div>
      </Card>
    </AppLayout>
  );
}
