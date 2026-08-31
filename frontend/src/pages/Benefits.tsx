import { useState } from 'react';
import AppLayout from '../components/shared/AppLayout';
import { Card, SectionHeading, Badge, EmptyState } from '../components/ui/Primitives';
import { useApiData } from '../hooks/useApiData';
import { ErrorState, LoadingState } from '../components/shared/DataState';
import { getBenefits } from '../api/services';
import { formatINR } from '../utils/format';
import { Landmark, ChevronRight, CheckCircle2, FileText, ListChecks } from 'lucide-react';

interface Scheme {
  code: string;
  name: string;
  limit: number | null;
  description: string;
  benefits: string[];
  eligibility: 'High' | 'Medium' | string;
  documents_needed: string[];
  potential_savings: number | null;
}

const eligibilityTone: Record<string, 'low' | 'medium' | 'neutral'> = {
  High: 'low',
  Medium: 'medium',
};

function SchemeCard({ scheme }: { scheme: Scheme }) {
  const [open, setOpen] = useState(false);

  return (
    <div className={`rounded-xl border transition-all duration-200 ${open ? 'border-primary/40 bg-primary/2' : 'border-line hover:border-primary/25'}`}>
      <button
        onClick={() => setOpen((p) => !p)}
        className="w-full flex items-center gap-4 p-4 text-left cursor-pointer"
      >
        <span className="ledger-num text-[11px] font-bold text-primary bg-primary/10 w-8 h-8 rounded-lg flex items-center justify-center shrink-0">
          {scheme.code}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5 flex-wrap">
            <p className="text-[13.5px] font-semibold text-ink">{scheme.name}</p>
            <Badge tone={eligibilityTone[scheme.eligibility] ?? 'neutral'}>{scheme.eligibility} match</Badge>
          </div>
          <p className="text-[11.5px] text-ink-soft">
            {scheme.limit != null ? `Limit ${formatINR(scheme.limit)}` : 'No fixed statutory limit'}
          </p>
        </div>
        <div className="text-right shrink-0">
          {scheme.potential_savings != null ? (
            <>
              <p className="ledger-num text-[14px] font-bold text-teal">{formatINR(scheme.potential_savings)}</p>
              <p className="text-[10.5px] text-ink-soft">potential saving</p>
            </>
          ) : (
            <p className="text-[11.5px] font-semibold text-ink-soft">Varies by usage</p>
          )}
        </div>
        <ChevronRight size={14} className={`text-ink-soft transition-transform shrink-0 ${open ? 'rotate-90' : ''}`} />
      </button>
      {open && (
        <div className="px-4 pb-4 border-t border-line">
          {scheme.description && (
            <p className="text-[13px] text-ink-soft leading-relaxed mt-3 mb-3">{scheme.description}</p>
          )}
          {scheme.benefits.length > 0 && (
            <div className="mb-3">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft mb-1.5">Benefits</p>
              <div className="space-y-1.5">
                {scheme.benefits.map((b, i) => (
                  <div key={i} className="flex items-start gap-2">
                    <CheckCircle2 size={13} className="text-teal mt-0.5 shrink-0" />
                    <p className="text-[12.5px] text-ink">{b}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
          {scheme.documents_needed.length > 0 && (
            <div className="flex items-start gap-2 p-3 rounded-lg bg-paper border border-line">
              <FileText size={13} className="text-primary mt-0.5 shrink-0" />
              <p className="text-[12px] text-ink-soft">
                <span className="font-medium text-ink">Documents needed: </span>
                {scheme.documents_needed.join(', ')}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function Benefits() {
  const state = useApiData<any>(() => getBenefits(), []);

  if (state.loading) return <AppLayout title="Benefits & Schemes"><LoadingState /></AppLayout>;
  if (state.error)
    return (
      <AppLayout title="Benefits & Schemes">
        <ErrorState error={state.error} onRetry={state.refetch} what="government schemes you may qualify for" />
      </AppLayout>
    );

  const d: any = state.data ?? {};
  const schemes = (d.scheme_details ?? []) as Scheme[];
  const topRecommendations = (d.top_recommendations ?? []) as Scheme[];
  const categories = (d.categories ?? {}) as Record<string, string[]>;
  const actionItems = (d.action_items ?? []) as string[];

  return (
    <AppLayout title="Benefits & Schemes" subtitle="Government schemes and Chapter VI-A deductions matched to your real profile">

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-6 stagger">
        <div className="rounded-2xl bg-gradient-to-br from-navy to-navy-deep text-white p-6 relative overflow-hidden">
          <div className="absolute -right-10 -top-10 w-56 h-56 rounded-full bg-gradient-to-br from-saffron/20 to-teal/10 blur-2xl" />
          <div className="relative">
            <div className="flex items-center gap-2 mb-3">
              <Landmark size={18} className="text-saffron" />
              <p className="text-[11px] font-semibold uppercase tracking-wide text-white/60">Matched to your profile</p>
            </div>
            <p className="font-display font-bold text-[28px] leading-tight mb-1">
              {formatINR(d.total_potential_savings)}
            </p>
            <p className="text-[13px] text-white/60">total potential saving across {schemes.length} scheme{schemes.length === 1 ? '' : 's'}</p>
          </div>
        </div>

        <Card className="p-6">
          <p className="text-[11px] font-semibold tracking-wide uppercase text-primary mb-2">Schemes found</p>
          <p className="ledger-num font-display font-semibold text-[28px] text-ink mb-1">{d.schemes_found ?? 0}</p>
          <p className="text-[12.5px] text-ink-soft">across {Object.keys(categories).length} categor{Object.keys(categories).length === 1 ? 'y' : 'ies'}</p>
        </Card>

        <Card className="p-6">
          <p className="text-[11px] font-semibold tracking-wide uppercase text-primary mb-2">Top pick</p>
          {topRecommendations[0] ? (
            <>
              <p className="text-[15px] font-semibold text-ink mb-1 truncate">{topRecommendations[0].name}</p>
              <p className="text-[12.5px] text-ink-soft">{topRecommendations[0].code}</p>
            </>
          ) : (
            <p className="text-[13px] text-ink-soft">Complete your profile to see a recommendation.</p>
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <Card className="lg:col-span-2 p-6">
          <SectionHeading
            eyebrow="Matched Schemes"
            title="Schemes you qualify for"
            action={<Badge tone="neutral">{schemes.length} found</Badge>}
          />
          {schemes.length ? (
            <div className="space-y-2 mt-2 stagger">
              {schemes.map((s) => <SchemeCard key={s.code} scheme={s} />)}
            </div>
          ) : (
            <EmptyState
              icon={Landmark}
              title="No schemes matched yet"
              message="Complete your financial profile — age, employment type, and existing cover — so schemes can be matched against your real situation."
            />
          )}
        </Card>

        <Card className="p-6">
          <SectionHeading eyebrow="Next Steps" title="Action items" action={<ListChecks size={18} className="text-primary" />} />
          {actionItems.length ? (
            <div className="space-y-2.5">
              {actionItems.map((a, i) => (
                <div key={i} className="flex items-start gap-2.5 py-2 border-b border-line last:border-0">
                  <span className="ledger-num text-[11px] font-semibold text-primary bg-primary/10 w-6 h-6 rounded-md flex items-center justify-center shrink-0">
                    {i + 1}
                  </span>
                  <p className="text-[12.5px] text-ink leading-relaxed">{a}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-[13px] text-ink-soft">Nothing outstanding right now.</p>
          )}

          {Object.keys(categories).length > 0 && (
            <div className="mt-5 pt-5 border-t border-line">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft mb-2">By category</p>
              <div className="space-y-1.5">
                {Object.entries(categories).map(([cat, names]) => (
                  <div key={cat} className="flex items-center justify-between text-[12.5px]">
                    <span className="text-ink-soft">{cat}</span>
                    <span className="ledger-num text-ink font-medium">{names.length}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      </div>
    </AppLayout>
  );
}
