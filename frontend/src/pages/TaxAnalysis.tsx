import { useState, useEffect } from 'react';
import AppLayout from '../components/shared/AppLayout';
import { Card, SectionHeading, Badge } from '../components/ui/Primitives';
import { DeductionPie } from '../components/shared/Charts';
import { useApiData } from '../hooks/useApiData';
import { calculateAdvancedTax } from '../api/services';
import { formatINR, formatPercent } from '../utils/format';
import {
  Calculator, TrendingDown, PiggyBank, RefreshCw, ArrowRight, CheckCircle, AlertCircle,
} from 'lucide-react';
import {
  useProfileStore, calculateTax, taxFromTaxable, marginalRateAt,
  NEW_REGIME_SLABS, OLD_REGIME_SLABS, STD_DEDUCTION_NEW, STD_DEDUCTION_OLD,
  SECTION_80C_LIMIT, SECTION_24B_LIMIT, SECTION_80CCD_1B_LIMIT,
  REBATE_87A_THRESHOLD_NEW, REBATE_87A_THRESHOLD_OLD,
  TAX_YEAR, ASSESSMENT_YEAR,
} from '../store/useProfileStore';
import { Link } from 'react-router-dom';

interface RowProps {
  label: string;
  value: string | number;
  strong?: boolean;
  indent?: boolean;
  highlight?: 'saving' | 'warn';
}

const ROW = ({ label, value, strong, indent, highlight }: RowProps) => (
  <div className={`flex items-center justify-between py-2.5 border-b border-line last:border-0 ${indent ? 'pl-4' : ''}`}>
    <span className={`text-[13.5px] ${strong ? 'font-semibold text-ink' : 'text-ink-soft'}`}>{label}</span>
    <span className={`ledger-num text-[14px] ${
      strong ? 'font-semibold text-ink' : highlight === 'saving' ? 'font-semibold text-teal' : highlight === 'warn' ? 'font-semibold text-saffron' : 'text-ink-soft'
    }`}>{value}</span>
  </div>
);

// Client-side what-if estimator — shares slab data and 87A marginal-relief
// logic with the store's `calculateTax` via `taxFromTaxable` so this tool
// can't silently drift out of sync with the real calculation (a duplicate
// hardcoded rebate cliff here caused exactly that drift previously).
function computeTax(income: number, deductions: number, regime: 'new' | 'old') {
  const stdDed = regime === 'new' ? STD_DEDUCTION_NEW : STD_DEDUCTION_OLD;
  const taxable = Math.max(0, income - deductions - stdDed);
  const { incomeTax: tax, cess, totalTax: total } = taxFromTaxable(taxable, regime);
  const rate = income > 0 ? (total / income) * 100 : 0;
  return { taxable, tax, cess, total, rate };
}

export default function TaxAnalysis() {
  const state = useApiData<any>(() => calculateAdvancedTax({}), []);
  const t: any = state.data ?? {};
  // The backend is the source of truth whenever it has actually returned a
  // result — `calculateTax(profile)` below is a client-side estimate that
  // exists for instant feedback while the API call is in flight (or as a
  // fallback if it errors), never a substitute once the real figure lands.
  const apiTaxReady = !state.loading && !state.error && t.tax_calculation != null;

  const { profile } = useProfileStore();
  const profileTax = calculateTax(profile);
  const hasProfile = profileTax.grossIncome > 0;

  const [income, setIncome] = useState(hasProfile ? profileTax.grossIncome : (t.gross_income ?? 0));
  const [deductions, setDeductions] = useState(hasProfile ? profileTax.totalDeductions - (profile.taxRegime === 'new' ? STD_DEDUCTION_NEW : STD_DEDUCTION_OLD) : (t.total_deductions ?? 0));
  const [regime, setRegime] = useState<'new' | 'old'>(profile.taxRegime || 'new');

  useEffect(() => {
    if (hasProfile) {
      setIncome(profileTax.grossIncome);
      setRegime(profile.taxRegime);
    } else if (t.gross_income != null) {
      // No local profile yet — seed the what-if tool from the demo/API
      // figures once they arrive, instead of leaving it stuck at the ₹0
      // fallback the initial useState had to use before this data existed.
      setIncome(t.gross_income);
      setDeductions(t.total_deductions ?? 0);
    }
  }, [profile, hasProfile, t.gross_income]);

  const estimate = computeTax(income, deductions, regime);

  // Deduction breakdown from profile or mock
  const deductionBreakdown = hasProfile ? [
    { name: '80C (ELSS/PPF/LIC)', value: Math.min(profile.ppf + profile.elss + profile.lic + profile.ulip + profile.fd5yr + profile.sukanyaSamriddhi + profile.nsc + profile.homeLoanPrincipal, SECTION_80C_LIMIT), limit: SECTION_80C_LIMIT },
    { name: '80CCD(1B) NPS', value: Math.min(profile.npsEmployee, SECTION_80CCD_1B_LIMIT), limit: SECTION_80CCD_1B_LIMIT },
    { name: '80D Health Ins.', value: profile.healthInsuranceSelf + profile.healthInsuranceParents, limit: 75000 },
    { name: 'Sec 24b Home Loan', value: Math.min(profile.homeLoanInterest, SECTION_24B_LIMIT), limit: SECTION_24B_LIMIT },
    { name: '80E Edu Loan', value: profile.eduLoanInterest, limit: null },
    { name: 'HRA + LTA', value: profile.hra + profile.lta, limit: null },
  ].filter((d) => d.value > 0) : [];

  return (
    <AppLayout title="Tax Analysis" subtitle={`Income, deductions & live what-if calculator · ${TAX_YEAR} / ${ASSESSMENT_YEAR}`}>

      {/* Profile-sourced summary */}
      {hasProfile && apiTaxReady && (
        <div className="flex items-center gap-2 mb-5 px-4 py-3 rounded-xl bg-teal/8 border border-teal/20">
          <CheckCircle size={14} className="text-teal shrink-0" />
          <p className="text-[12.5px] text-ink">
            Showing server-computed calculations for your <span className="font-semibold">financial profile</span>.{' '}
            <Link to="/profile" className="text-primary font-semibold underline">Edit profile →</Link>
          </p>
        </div>
      )}

      {hasProfile && !apiTaxReady && (
        <div className="flex items-center gap-2 mb-5 px-4 py-3 rounded-xl bg-saffron/8 border border-saffron/20">
          <AlertCircle size={14} className="text-saffron shrink-0" />
          <p className="text-[12.5px] text-ink-soft">
            Showing an instant estimate from your profile while the server-computed figure loads.
          </p>
        </div>
      )}

      {!hasProfile && (
        <div className="flex items-center gap-2 mb-5 px-4 py-3 rounded-xl bg-saffron/8 border border-saffron/20">
          <AlertCircle size={14} className="text-saffron shrink-0" />
          <p className="text-[12.5px] text-ink-soft">
            Showing demo data. <Link to="/profile" className="text-primary font-semibold underline">Complete your profile</Link> for personalised calculations.
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-6 stagger">
        {/* Income & Liability */}
        <Card className="lg:col-span-2 p-6">
          <SectionHeading eyebrow={`${TAX_YEAR} · ${regime === 'new' ? 'New Regime' : 'Old Regime'}`} title="Income & Liability Summary" />

          {hasProfile ? (
            <>
              {profile.salaryCtc > 0 && <ROW label="Salary income (CTC)" value={formatINR(profile.salaryCtc)} />}
              {profile.businessIncome > 0 && <ROW label="Business income" value={formatINR(profile.businessIncome)} />}
              {profile.freelanceIncome > 0 && <ROW label="Freelance income" value={formatINR(profile.freelanceIncome)} />}
              {profile.rentalIncome > 0 && <ROW label="Rental income" value={formatINR(profile.rentalIncome)} />}
              {profile.capitalGainsStcg > 0 && <ROW label="Capital gains — STCG (15%)" value={formatINR(profile.capitalGainsStcg)} />}
              {profile.capitalGainsLtcg > 0 && <ROW label="Capital gains — LTCG (10% above ₹1L)" value={formatINR(profile.capitalGainsLtcg)} />}
              {profile.otherIncome > 0 && <ROW label="Other income" value={formatINR(profile.otherIncome)} />}
              <ROW label="Gross total income" value={formatINR(profileTax.grossIncome)} strong />

              <div className="my-1" />
              <ROW label={`Standard deduction (${regime === 'new' ? 'New regime' : 'Old regime'})`} value={`− ${formatINR(regime === 'new' ? STD_DEDUCTION_NEW : STD_DEDUCTION_OLD)}`} highlight="saving" indent />
              {regime === 'old' && profileTax.totalDeductions > (STD_DEDUCTION_OLD) && (
                <ROW label="Section 80C / 80D / 80E / 24b deductions" value={`− ${formatINR(profileTax.totalDeductions - STD_DEDUCTION_OLD)}`} highlight="saving" indent />
              )}
              <ROW label="Total deductions" value={`− ${formatINR(profileTax.totalDeductions)}`} strong />
              <ROW label="Taxable income" value={formatINR(apiTaxReady ? t.taxable_income : profileTax.taxableIncome)} strong />

              <div className="my-1" />
              <ROW label="Income tax (slab)" value={formatINR(apiTaxReady ? t.tax_calculation?.income_tax : profileTax.incomeTax)} />
              {profileTax.taxableIncome <= (regime === 'new' ? REBATE_87A_THRESHOLD_NEW : REBATE_87A_THRESHOLD_OLD) && (
                <ROW label="Rebate u/s 87A (zero tax!)" value="− ₹0 liability" highlight="saving" indent />
              )}
              <ROW label="Health & Education Cess (4%)" value={formatINR(apiTaxReady ? t.tax_calculation?.cess : profileTax.cess)} />
              <ROW label="Total tax liability" value={formatINR(apiTaxReady ? t.tax_calculation?.total_tax_liability : profileTax.totalTax)} strong />
              <ROW label="Effective tax rate" value={formatPercent(apiTaxReady ? t.effective_tax_rate : profileTax.effectiveRate)} strong />
            </>
          ) : (
            <>
              <ROW label="Salary income" value={formatINR(t.income_breakdown?.salary)} />
              <ROW label="Rental income" value={formatINR(t.income_breakdown?.rental)} />
              <ROW label="Capital gains (STCG + LTCG)" value={formatINR((t.income_breakdown?.capital_gains_stcg || 0) + (t.income_breakdown?.capital_gains_ltcg || 0))} />
              <ROW label="Gross total income" value={formatINR(t.gross_income)} strong />
              <ROW label="Standard deduction (New Regime)" value={`− ${formatINR(STD_DEDUCTION_NEW)}`} highlight="saving" indent />
              <ROW label="Total deductions" value={`− ${formatINR(t.total_deductions)}`} />
              <ROW label="Taxable income" value={formatINR(t.taxable_income)} strong />
              <ROW label="Income tax" value={formatINR(t.tax_calculation?.income_tax)} />
              <ROW label="Health & Education Cess (4%)" value={formatINR(t.tax_calculation?.cess)} />
              <ROW label="Total tax liability" value={formatINR(t.tax_calculation?.total_tax_liability)} strong />
            </>
          )}
        </Card>

        {/* Deduction breakdown */}
        <Card className="p-6">
          <SectionHeading eyebrow="Section-wise" title="Deduction Mix" />
          {deductionBreakdown.some((d) => d.value > 0) ? (
            <>
              <DeductionPie data={deductionBreakdown} />
              <div className="space-y-2 mt-2">
                {deductionBreakdown.filter((d) => d.value > 0).map((d) => (
                  <div key={d.name} className="flex items-center justify-between text-[12.5px]">
                    <span className="text-ink-soft">{d.name}</span>
                    <span className="ledger-num text-ink font-medium">{formatINR(d.value)}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center text-center h-40">
              <p className="text-[13px] text-ink-soft">Fill in your investments in your</p>
              <Link to="/profile" className="text-primary font-semibold text-[13px] mt-1 flex items-center gap-1">
                Profile <ArrowRight size={13} />
              </Link>
            </div>
          )}
        </Card>
      </div>

      {/* Slab reference — derived from the same NEW_REGIME_SLABS / OLD_REGIME_SLABS
          the real calculation uses, so this table can't go stale independently
          of the engine the way a hand-typed copy of the slabs previously did. */}
      <Card className="p-6 mb-6">
        <SectionHeading eyebrow={`${TAX_YEAR} Tax Slabs`} title="Reference — New vs Old Regime" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-2 stagger">
          {/* New Regime */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Badge tone="low">New Regime (Default)</Badge>
              <span className="text-[11.5px] text-ink-soft">{formatINR(STD_DEDUCTION_NEW)} std deduction · no 80C/D</span>
            </div>
            <div className="space-y-0">
              {NEW_REGIME_SLABS.map((s, i) => (
                <div key={s.min} className="flex justify-between py-2 border-b border-line last:border-0 text-[12.5px]">
                  <span className="text-ink-soft">
                    {s.max === Infinity ? `Above ${formatINR(s.min)}` : `${formatINR(s.rate === 0 ? s.min : s.min + 1)} – ${formatINR(s.max)}`}
                    {i === 1 && <span className="text-[11px] text-teal"> (0 if ≤ {formatINR(REBATE_87A_THRESHOLD_NEW)} after 87A)</span>}
                  </span>
                  <span className="ledger-num font-semibold text-ink">{s.rate === 0 ? 'Nil' : `${s.rate * 100}%`}</span>
                </div>
              ))}
            </div>
          </div>
          {/* Old Regime */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Badge tone="neutral">Old Regime</Badge>
              <span className="text-[11.5px] text-ink-soft">{formatINR(STD_DEDUCTION_OLD)} std · all 80C/D deductions</span>
            </div>
            <div className="space-y-0">
              {OLD_REGIME_SLABS.map((s) => (
                <div key={s.min} className="flex justify-between py-2 border-b border-line last:border-0 text-[12.5px]">
                  <span className="text-ink-soft">
                    {s.max === Infinity ? `Above ${formatINR(s.min)}` : `${formatINR(s.rate === 0 ? s.min : s.min + 1)} – ${formatINR(s.max)}`}
                    {s.rate === 0.05 && <span className="text-[11px] text-teal"> (0 if ≤ {formatINR(REBATE_87A_THRESHOLD_OLD)} after 87A)</span>}
                  </span>
                  <span className="ledger-num font-semibold text-ink">{s.rate === 0 ? 'Nil' : `${s.rate * 100}%`}</span>
                </div>
              ))}
              <div className="mt-2 text-[11.5px] text-ink-soft space-y-1">
                <p>+ {formatINR(STD_DEDUCTION_OLD)} standard deduction</p>
                <p>+ Section 80C up to {formatINR(SECTION_80C_LIMIT)}</p>
                <p>+ Section 80D, 24b, 80E, HRA, LTA</p>
                <p className="text-teal">+ 4% Health & Education Cess on all regimes</p>
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* What-if calculator */}
      <Card className="p-6">
        <SectionHeading
          eyebrow="What-if Calculator"
          title="Model a different scenario"
          action={<Badge tone="neutral"><Calculator size={12} /> {TAX_YEAR} slabs</Badge>}
        />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mt-2">
          <div className="space-y-5">
            {/* Regime toggle */}
            <div>
              <p className="text-[13px] font-medium text-ink mb-2">Tax Regime</p>
              <div className="flex gap-2">
                {(['new', 'old'] as const).map((r) => (
                  <button
                    key={r}
                    onClick={() => setRegime(r)}
                    className={`flex-1 h-9 rounded-lg border text-[13px] font-semibold transition-all ${
                      regime === r ? 'border-primary bg-primary/10 text-primary' : 'border-line text-ink-soft hover:border-primary/30'
                    }`}
                  >
                    {r === 'new' ? 'New Regime' : 'Old Regime'}
                  </button>
                ))}
              </div>
            </div>

            {/* Income slider */}
            <div>
              <div className="flex justify-between mb-2">
                <label className="text-[13px] font-medium text-ink">Gross annual income</label>
                <span className="ledger-num text-[13px] font-semibold text-primary">{formatINR(income)}</span>
              </div>
              <input
                type="range" min="300000" max="10000000" step="50000"
                value={income} onChange={(e) => setIncome(Number(e.target.value))}
                className="w-full accent-primary"
              />
              <div className="flex justify-between text-[10.5px] text-ink-soft mt-1">
                <span>₹3L</span><span>₹1Cr</span>
              </div>
            </div>

            {/* Deductions slider (old regime only) */}
            {regime === 'old' && (
              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-[13px] font-medium text-ink">Additional deductions (80C, 80D…)</label>
                  <span className="ledger-num text-[13px] font-semibold text-primary">{formatINR(deductions)}</span>
                </div>
                <input
                  type="range" min="0" max="500000" step="5000"
                  value={deductions} onChange={(e) => setDeductions(Number(e.target.value))}
                  className="w-full accent-primary"
                />
                <div className="flex justify-between text-[10.5px] text-ink-soft mt-1">
                  <span>₹0</span><span>₹5L</span>
                </div>
              </div>
            )}

            <p className="text-[11.5px] text-ink-soft leading-relaxed flex items-start gap-1.5">
              <RefreshCw size={12} className="mt-0.5 shrink-0" />
              Using official {TAX_YEAR} slabs with Section 87A marginal-relief rebate and 4% cess. Standard deduction applied automatically.
            </p>
          </div>

          <div className="rounded-2xl bg-paper border border-line p-6 flex flex-col justify-center">
            <div className="flex items-center gap-2 mb-5">
              <div className="w-8 h-8 rounded-lg bg-teal/10 text-teal flex items-center justify-center"><TrendingDown size={16} /></div>
              <div>
                <p className="text-[12px] text-ink-soft">Estimated total tax</p>
                <p className="text-[11px] text-ink-soft">{regime === 'new' ? 'New Regime' : 'Old Regime'} · {TAX_YEAR}</p>
              </div>
            </div>
            <p className="ledger-num font-display font-bold text-[34px] text-ink mb-1">{formatINR(estimate.total)}</p>
            <p className="text-[12.5px] text-ink-soft mb-5">
              {formatPercent(estimate.rate)} effective rate on taxable income of {formatINR(estimate.taxable)}
            </p>
            <div className="space-y-2 text-[12.5px]">
              <div className="flex justify-between py-1.5 border-b border-line">
                <span className="text-ink-soft">Income tax (slab)</span>
                <span className="ledger-num text-ink">{formatINR(estimate.tax)}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-line">
                <span className="text-ink-soft">Cess (4%)</span>
                <span className="ledger-num text-ink">{formatINR(estimate.cess)}</span>
              </div>
              {estimate.taxable <= (regime === 'new' ? REBATE_87A_THRESHOLD_NEW : REBATE_87A_THRESHOLD_OLD) && estimate.taxable > 0 && (
                <div className="flex items-center gap-2 pt-2 text-teal">
                  <CheckCircle size={13} />
                  <span className="text-[12px] font-semibold">Section 87A rebate applied — ₹0 tax!</span>
                </div>
              )}
            </div>
            <div className="flex items-center gap-2 pt-4 mt-2 border-t border-line">
              <PiggyBank size={15} className="text-saffron" />
              <p className="text-[12px] text-ink-soft">
                {regime === 'old'
                  ? `Each ₹10,000 in deductions saves ~₹${(10000 * marginalRateAt(estimate.taxable, 'old') * 1.04).toFixed(0)} in tax at your current marginal rate.`
                  : `New regime: No 80C/80D deductions. Standard deduction of ${formatINR(STD_DEDUCTION_NEW)} applies.`}
              </p>
            </div>
          </div>
        </div>
      </Card>
    </AppLayout>
  );
}
