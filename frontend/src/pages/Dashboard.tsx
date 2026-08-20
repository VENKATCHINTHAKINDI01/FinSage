import { IndianRupee, Percent, ShieldCheck, Wallet, Sparkles, ArrowRight, Zap, UserCircle, AlertTriangle, CheckCircle2 } from 'lucide-react';
import ParticleField from '../components/common/ParticleField';
import AppLayout from '../components/shared/AppLayout';
import StatCard from '../components/ui/StatCard';
import ScoreGauge from '../components/ui/ScoreGauge';
import { Card, SectionHeading, Badge } from '../components/ui/Primitives';
import { useApiData } from '../hooks/useApiData';
import { EmptyState } from '../components/shared/DataState';
import { getHealthScore, calculateAdvancedTax } from '../api/services';
import { formatINR, formatCompactINR, formatPercent } from '../utils/format';
import { Link } from 'react-router-dom';
import { useProfileStore, calculateTax, marginalRateAt, TAX_YEAR, ASSESSMENT_YEAR, FY_END_DATE } from '../store/useProfileStore';
import { useAuthStore } from '../store/useAuthStore';
import type { FinancialProfile } from '../store/useProfileStore';

// Profile-aware smart suggestions.
//
// Every `potential_savings` figure below is an ESTIMATE, valued at the real
// marginal slab rate for this income (marginalRateAt), never a flat assumed
// bracket — a flat 30% overstates savings for anyone not in the top slab,
// a flat 10% understates it for anyone who is. Labelled "Estimated" in the
// UI; the confirmed figure comes from POST /api/v1/compliance/calculator.
//
// Deliberately NOT suggested here: Section 80EEB (EV loan interest). Its
// loan-sanction window closed 31 March 2023 — this function has no way to
// evaluate date-windowed eligibility, and a suggestion that cannot check its
// own eligibility window is exactly the "80EEB trap" this product exists to
// avoid (see docs/IMPLEMENTATION_PLAN.md §2.2). Window-aware benefit
// eligibility is the backend's date-windowed eligibility DSL's job, not a
// client-side guess.
function getProfileSuggestions(profile: FinancialProfile, tax: ReturnType<typeof calculateTax>) {
  const suggestions: { strategy: string; action: string; potential_savings: number }[] = [];
  const marginalRate = marginalRateAt(tax.taxableIncome, tax.regime);
  const fyEnd = FY_END_DATE;

  const sec80CUsed = profile.ppf + profile.elss + profile.lic + profile.ulip + profile.fd5yr + profile.nsc + profile.homeLoanPrincipal;
  if (sec80CUsed < 150000 && tax.grossIncome > 0) {
    suggestions.push({
      strategy: `Maximize Section 80C — ₹${(150000 - Math.min(sec80CUsed, 150000)).toLocaleString('en-IN')} headroom left`,
      action: `Invest in ELSS, PPF, or NSC before ${fyEnd}`,
      potential_savings: Math.max(0, 150000 - sec80CUsed) * marginalRate,
    });
  }

  if (profile.npsEmployee < 50000 && tax.grossIncome > 0) {
    suggestions.push({
      strategy: 'NPS Tier-I extra deduction (80CCD(1B)) — outside 80C limit',
      action: `Invest up to ₹${(50000 - profile.npsEmployee).toLocaleString('en-IN')} more in NPS for extra deduction`,
      potential_savings: Math.max(0, 50000 - profile.npsEmployee) * marginalRate,
    });
  }

  if (profile.healthInsuranceSelf < 25000 && tax.grossIncome > 0 && tax.regime === 'old') {
    suggestions.push({
      strategy: 'Health insurance (80D) — ₹25K deduction for self + family',
      action: `Buy or upgrade health insurance before ${fyEnd}`,
      potential_savings: Math.max(0, 25000 - profile.healthInsuranceSelf) * marginalRate,
    });
  }

  if (profile.profession === 'salaried' && profile.npsEmployer === 0 && profile.salaryCtc > 0) {
    // 10% of salary is the real s.80CCD(2) statutory limit for non-
    // government employees, not an assumption — only the rupee-savings
    // conversion below uses the (estimated) marginal rate.
    const employerNpsLimit = profile.salaryCtc * 0.10;
    suggestions.push({
      strategy: 'Ask employer for NPS contribution (80CCD(2)) — completely outside 80C',
      action: `Up to ₹${Math.round(employerNpsLimit).toLocaleString('en-IN')} tax-free via employer NPS contribution`,
      potential_savings: employerNpsLimit * marginalRate,
    });
  }

  // Regime comparison — both totals are the same marginal-relief-aware
  // calculateTax(), so this comparison is internally consistent even though
  // it is still a client-side estimate pending the API result.
  const newT = calculateTax({ ...profile, taxRegime: 'new' });
  const oldT = calculateTax({ ...profile, taxRegime: 'old' });
  const currentT = tax.regime === 'new' ? newT : oldT;
  const otherT = tax.regime === 'new' ? oldT : newT;
  if (otherT.totalTax < currentT.totalTax - 5000) {
    const better = tax.regime === 'new' ? 'Old Regime' : 'New Regime';
    suggestions.push({
      strategy: `Switch to ${better} — saves ₹${(currentT.totalTax - otherT.totalTax).toLocaleString('en-IN')} this year`,
      action: `You're on ${tax.regime === 'new' ? 'New' : 'Old'} regime but ${better} is more beneficial for your income profile`,
      potential_savings: currentT.totalTax - otherT.totalTax,
    });
  }

  return suggestions.sort((a, b) => b.potential_savings - a.potential_savings).slice(0, 4);
}

export default function Dashboard() {
  const healthState = useApiData<any>(getHealthScore, []);
  const taxState = useApiData<any>(() => calculateAdvancedTax({}), []);

  // No fabricated fallback (DEM-002). Where the API has not returned, the
  // figure is absent and the card renders an em dash rather than an invention.
  const h: any = healthState.data?.result ?? {};
  const t: any = taxState.data ?? {};

  const { profile, completeness } = useProfileStore();
  const user = useAuthStore((s) => s.user);
  const profileTax = calculateTax(profile);
  const hasProfile = profileTax.grossIncome > 0;

  // The API result — POST /api/v1/compliance/calculator, backed by
  // backend.core — is authoritative whenever it has actually returned.
  // The local `profileTax` estimate is a stand-in ONLY while that request is
  // still in flight or has failed; it is never preferred over a real answer
  // that has already arrived, which is what this precedence used to do for
  // every user who had filled in a profile — precisely the group the real
  // number matters most for. Drives the "Estimated" labelling in the JSX
  // below rather than presenting either figure as equally certain.
  const apiTaxReady = !taxState.loading && !taxState.error && t.tax_calculation != null;

  const displayTax = apiTaxReady ? t.tax_calculation?.total_tax_liability : (hasProfile ? profileTax.totalTax : undefined);
  const displayGross = apiTaxReady ? t.gross_income : (hasProfile ? profileTax.grossIncome : undefined);
  const displayDeductions = apiTaxReady ? t.total_deductions : (hasProfile ? profileTax.totalDeductions : undefined);
  const displayRate: number | undefined = apiTaxReady ? t.effective_tax_rate : (hasProfile ? profileTax.effectiveRate : undefined);
  const displayTaxable = apiTaxReady ? t.taxable_income : (hasProfile ? profileTax.taxableIncome : undefined);

  // Suggestions: prefer the backend's (grounded in real tool results, per
  // AGT-001 — see backend/agents/tax_optimizer.py) whenever it has real
  // figures to offer; the client estimate fills in only while that has not
  // loaded, or offers nothing of its own.
  const apiSuggestions = (t.optimization_suggestions ?? []).filter((s: any) => s?.savings != null);
  const profileSuggestions = hasProfile ? getProfileSuggestions(profile, profileTax) : [];
  const suggestionsToShow = apiTaxReady && apiSuggestions.length > 0
    ? apiSuggestions.slice(0, 4)
    : profileSuggestions;
  const suggestionsAreEstimate = !(apiTaxReady && apiSuggestions.length > 0) && suggestionsToShow.length > 0;

  const totalPotentialSavings = apiTaxReady && t.total_potential_savings != null
    ? t.total_potential_savings
    : (hasProfile ? profileSuggestions.reduce((a, s) => a + s.potential_savings, 0) : undefined);

  return (
    <AppLayout title="Dashboard" subtitle={`Your complete financial picture · ${TAX_YEAR} / ${ASSESSMENT_YEAR}`}>
      {/* Cosmic particle background */}
      <div className="fixed inset-0 pointer-events-none z-0 hidden dark:block">
        <ParticleField theme="cosmic" count={30} />
      </div>

      {/* Data Quality Indicator */}
      <div className="flex items-center gap-2 mb-4 animate-gravity-up">
        {apiTaxReady ? (
          <>
            <span className="badge-verified green">
              <CheckCircle2 size={12} />
              Data Validated
            </span>
            <span className="text-[11px] text-ink-soft dark:text-slate-500">
              Computed by the {TAX_YEAR} deterministic tax engine
            </span>
          </>
        ) : hasProfile ? (
          <>
            <span className="badge-verified yellow">
              <AlertTriangle size={12} />
              Estimated
            </span>
            <span className="text-[11px] text-ink-soft dark:text-slate-500">
              Instant preview from your profile — confirming with the server-computed figure
            </span>
          </>
        ) : null}
      </div>

      <div className="flex items-center justify-between mb-6">
        <div>
          <p className="text-[13px] text-ink-soft">
            {hasProfile
              ? `Welcome back, ${user?.name || 'there'} — live calculations based on your profile.`
              : 'Welcome back — complete your profile for personalised insights.'}
          </p>
        </div>
      </div>

      {/* Profile prompt banner */}
      {completeness < 50 && (
        <div className="flex items-center justify-between gap-3 p-4 mb-5 rounded-xl bg-primary/8 border border-primary/20">
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0">
              <UserCircle size={16} />
            </div>
            <div>
              <p className="text-[13.5px] font-semibold text-ink">Complete your financial profile</p>
              <p className="text-[12px] text-ink-soft mt-0.5">
                Your profile is {completeness}% complete. Add income, investments & assets to unlock personalised advice.
              </p>
            </div>
          </div>
          <Link
            to="/profile"
            className="shrink-0 h-9 px-4 rounded-lg bg-primary text-white text-[12.5px] font-semibold flex items-center gap-1.5 hover:bg-primary/90 transition-colors whitespace-nowrap"
          >
            Complete <ArrowRight size={13} />
          </Link>
        </div>
      )}

      {/* Hero row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-6 stagger">
        <Card className="lg:col-span-2 bg-gradient-to-br from-navy via-deep-ocean to-navy-deep text-white border-0 relative overflow-hidden">
          <div className="absolute -right-10 -top-10 w-56 h-56 rounded-full bg-gradient-to-br from-cosmic-cyan/20 to-cosmic-violet/10 blur-2xl animate-float" />
          <div className="absolute -left-16 -bottom-16 w-40 h-40 rounded-full bg-gradient-to-br from-cosmic-emerald/10 to-transparent blur-2xl animate-float-slow" />
          <div className="relative p-6">
            <p className="text-[11px] font-semibold tracking-wide uppercase text-white/60 mb-2">
              {apiTaxReady ? 'Tax Position' : 'Estimated Tax Position'} · {TAX_YEAR}
              {hasProfile ? ` · ${profile.taxRegime === 'new' ? 'New' : 'Old'} Regime` : ''}
            </p>
            <p className="ledger-num font-display font-semibold text-[38px] leading-none mb-1">
              {formatINR(displayTax)}
            </p>
            <p className="text-[13px] text-white/60 mb-6">
              {displayRate != null ? `Total liability at ${formatPercent(displayRate)} effective rate` : 'Complete your profile to see your tax position'}
            </p>

            <div className="grid grid-cols-3 gap-4 pt-5 border-t border-white/10">
              <div>
                <p className="ledger-num text-[16px] font-semibold">{formatCompactINR(displayGross)}</p>
                <p className="text-[11px] text-white/50">Gross income</p>
              </div>
              <div>
                <p className="ledger-num text-[16px] font-semibold">{formatCompactINR(displayDeductions)}</p>
                <p className="text-[11px] text-white/50">Deductions</p>
              </div>
              <div>
                <p className="ledger-num text-[16px] font-semibold text-saffron-light">
                  {formatCompactINR(totalPotentialSavings)}
                </p>
                <p className="text-[11px] text-white/50">Can still save</p>
              </div>
            </div>
          </div>
        </Card>

        <Card className="flex flex-col items-center justify-center text-center p-6">
          <p className="text-[11px] font-semibold tracking-wide uppercase text-primary mb-3">Financial Health</p>
          <ScoreGauge score={h.overall_score} />
          <p className="text-[12.5px] text-ink-soft mt-3">{h.health_status?.message}</p>
          <Link to="/health-score" className="mt-3 text-[12.5px] font-medium text-primary inline-flex items-center gap-1 hover:gap-1.5 transition-all">
            View breakdown <ArrowRight size={13} />
          </Link>
        </Card>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-5 mb-6 stagger">
        <StatCard label="Taxable income" value={formatCompactINR(displayTaxable)} icon={IndianRupee} accent="primary" />
        <StatCard label="Effective tax rate" value={formatPercent(displayRate)} icon={Percent} accent="saffron" />
        <StatCard
          label="Compliance score"
          value={h.compliance_status?.score != null ? `${h.compliance_status.score} / 100` : '—'}
          icon={ShieldCheck}
          accent="teal"
        />
        <StatCard label="Potential savings" value={formatCompactINR(totalPotentialSavings)} icon={Wallet} accent="saffron" />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5 mb-6 stagger">
        <Card className="lg:col-span-3 p-6">
          <SectionHeading eyebrow="4-Year Trend" title="Income vs. Tax Paid" />
          <EmptyState title="Not enough history yet" hint="Income and tax trends appear once you have filed through FinSage for more than one period." />
        </Card>
        <Card className="lg:col-span-2 p-6">
          <SectionHeading eyebrow="6-Month Trend" title="Health Score Trajectory" />
          <EmptyState title="No trend data yet" hint="Your health score is tracked monthly; the trend appears after your second score." />
        </Card>
      </div>

      {/* Smart Savings CTA */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-6 stagger">
        <Link to="/smart-savings" className="lg:col-span-1 block">
          <Card className="p-5 h-full border-dashed border-primary/30 hover:border-primary hover:bg-primary/3 transition-all cursor-pointer group">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-9 h-9 rounded-lg bg-saffron/10 text-saffron flex items-center justify-center">
                <Zap size={18} />
              </div>
              <div>
                <p className="text-[14px] font-bold text-ink">Smart Savings</p>
                <p className="text-[11.5px] text-ink-soft">Cost reduction engine</p>
              </div>
            </div>
            <p className="text-[12.5px] text-ink-soft leading-relaxed mb-3">
              Discover personalised strategies to cut taxes on vehicles, property, purchases & salary.
            </p>
            <span className="text-[12.5px] font-semibold text-primary flex items-center gap-1 group-hover:gap-2 transition-all">
              Explore strategies <ArrowRight size={13} />
            </span>
          </Card>
        </Link>

        {/* Recommendations */}
        <Card className="lg:col-span-2 p-6">
          <SectionHeading
            eyebrow={hasProfile ? 'AI Recommendations — Your Profile' : 'AI Recommendations'}
            title="Top opportunities right now"
            action={<Badge tone="medium"><Sparkles size={12} /> {suggestionsToShow.length} active</Badge>}
          />
          {!hasProfile && (
            <div className="flex items-start gap-2 mb-3 px-3 py-2 rounded-lg bg-saffron/8 border border-saffron/20">
              <AlertTriangle size={12} className="text-saffron mt-0.5 shrink-0" />
              <p className="text-[11.5px] text-ink-soft">Showing generic tips. <Link to="/profile" className="text-primary font-semibold underline">Add your income</Link> for personalised savings.</p>
            </div>
          )}
          {suggestionsAreEstimate && (
            <div className="flex items-start gap-2 mb-3 px-3 py-2 rounded-lg bg-primary/8 border border-primary/20">
              <AlertTriangle size={12} className="text-primary mt-0.5 shrink-0" />
              <p className="text-[11.5px] text-ink-soft">
                Estimated from your profile at your marginal rate — confirming with the server.
              </p>
            </div>
          )}
          <div className="ledger-rule mb-4" />
          <div className="space-y-0">
            {suggestionsToShow.map((s: any, i: number) => (
              <div key={i} className="flex items-center justify-between py-3 border-b border-line last:border-0">
                <div className="flex items-start gap-3">
                  <span className="ledger-num text-[11px] font-semibold text-primary bg-primary/10 w-6 h-6 rounded-md flex items-center justify-center shrink-0 mt-0.5">
                    {i + 1}
                  </span>
                  <div>
                    <p className="text-[13.5px] font-medium text-ink">{s.strategy}</p>
                    <p className="text-[12px] text-ink-soft">{s.action}</p>
                  </div>
                </div>
                <p className="ledger-num text-[14px] font-semibold text-teal whitespace-nowrap ml-4">
                  +{formatCompactINR(s.potential_savings)}
                </p>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </AppLayout>
  );
}
