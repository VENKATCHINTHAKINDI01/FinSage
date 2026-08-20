import { useState, useEffect } from 'react';
import AppLayout from '../components/shared/AppLayout';
import { Card } from '../components/ui/Primitives';
import { useProfileStore, calculateTax, marginalRateAt, TAX_YEAR, FY_END_DATE } from '../store/useProfileStore';
import { formatINR } from '../utils/format';
import {
  Zap, Car, Home, ShoppingBag, Wallet,
  CheckCircle, AlertTriangle, ChevronRight, Info, BarChart3, MessageCircle, LayoutGrid,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import PurchaseAdvisorChat from '../components/smartsavings/PurchaseAdvisorChat';

// ── Types ────────────────────────────────────────────────────────────────────

interface Strategy {
  id: string;
  title: string;
  section: string;
  // null where there's no principled way to price the strategy from profile
  // data alone (e.g. GST ITC eligibility, HUF formation) — showing a number
  // there would be a guess dressed up as a calculation, which is exactly
  // the fabrication pattern this app's tax figures are held to never do.
  saving: number | null;
  difficulty: 'easy' | 'medium' | 'advanced';
  description: string;
  action: string;
  applicable: boolean;
  reason?: string;    // why it's applicable/not
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const difficultyBadge = (d: Strategy['difficulty']) => {
  const map = {
    easy: 'bg-teal/15 text-teal',
    medium: 'bg-saffron/15 text-saffron',
    advanced: 'bg-primary/15 text-primary',
  };
  return (
    <span className={`text-[10.5px] font-semibold px-2 py-0.5 rounded-md ${map[d]}`}>
      {d.charAt(0).toUpperCase() + d.slice(1)}
    </span>
  );
};

// ── Strategy card ────────────────────────────────────────────────────────────

function StrategyCard({ s, index }: { s: Strategy; index: number }) {
  const [open, setOpen] = useState(false);
  if (!s.applicable) return null;
  return (
    <div className={`rounded-xl border transition-all duration-200 ${open ? 'border-primary/40 bg-primary/2' : 'border-line hover:border-primary/25'}`}>
      <button
        onClick={() => setOpen((p) => !p)}
        className="w-full flex items-center gap-4 p-4 text-left"
      >
        <span className="ledger-num text-[11px] font-bold text-primary bg-primary/10 w-7 h-7 rounded-lg flex items-center justify-center shrink-0">
          {index + 1}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5 flex-wrap">
            <p className="text-[13.5px] font-semibold text-ink">{s.title}</p>
            {difficultyBadge(s.difficulty)}
          </div>
          <p className="text-[11.5px] text-ink-soft">{s.section}</p>
        </div>
        <div className="text-right shrink-0">
          {s.saving != null ? (
            <>
              <p className="ledger-num text-[14px] font-bold text-teal">{formatINR(s.saving)}</p>
              <p className="text-[10.5px] text-ink-soft">potential saving</p>
            </>
          ) : (
            <p className="text-[11.5px] font-semibold text-ink-soft">Depends on your situation</p>
          )}
        </div>
        <ChevronRight size={14} className={`text-ink-soft transition-transform shrink-0 ${open ? 'rotate-90' : ''}`} />
      </button>
      {open && (
        <div className="px-4 pb-4 border-t border-line">
          <p className="text-[13px] text-ink-soft leading-relaxed mt-3 mb-3">{s.description}</p>
          <div className="flex items-start gap-2 p-3 rounded-lg bg-teal/8 border border-teal/20">
            <CheckCircle size={13} className="text-teal mt-0.5 shrink-0" />
            <p className="text-[12.5px] text-ink font-medium">{s.action}</p>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Category section ─────────────────────────────────────────────────────────

function Category({
  icon: Icon, title, color, strategies, totalSaving,
}: {
  icon: any; title: string; color: string; strategies: Strategy[]; totalSaving: number;
}) {
  const applicable = strategies.filter((s) => s.applicable);
  if (applicable.length === 0) return null;
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${color}`}>
            <Icon size={17} />
          </div>
          <div>
            <p className="text-[14px] font-bold text-ink">{title}</p>
            <p className="text-[11px] text-ink-soft">{applicable.length} strategies available</p>
          </div>
        </div>
        <div className="text-right">
          <p className="ledger-num text-[15px] font-bold text-teal">{formatINR(totalSaving)}</p>
          <p className="text-[10.5px] text-ink-soft">total potential</p>
        </div>
      </div>
      <div className="space-y-2 stagger">
        {applicable.map((s, i) => <StrategyCard key={s.id} s={s} index={i} />)}
      </div>
    </Card>
  );
}

// ── Main ─────────────────────────────────────────────────────────────────────

export default function SmartSavings() {
  const { profile, completeness, fetchProfile } = useProfileStore();
  
  useEffect(() => {
    fetchProfile();
  }, [fetchProfile]);

  const tax = calculateTax(profile);
  const isSalaried = profile.profession === 'salaried';
  const isBusiness = profile.profession === 'business_owner' || profile.profession === 'professional' || profile.profession === 'freelancer';
  const hasIncome = tax.grossIncome > 0;
  // Real per-regime slab lookup (was a hardcoded 5-tier table using stale
  // thresholds and ignoring regime entirely — old and new regime slabs
  // differ substantially, so the same table couldn't have been right for
  // both).
  const marginalRate = marginalRateAt(tax.taxableIncome, profile.taxRegime);

  // ── Vehicle strategies ────────────────────────────────────────────────────
  const vehicleStrategies: Strategy[] = [
    {
      id: 'ev-loan',
      title: 'EV Loan Interest Deduction',
      section: 'Section 80EEB — up to ₹1,50,000',
      saving: Math.min(150000, Math.max(0, 150000 - profile.evLoanInterest)) * marginalRate,
      difficulty: 'easy',
      applicable: profile.hasVehicle && profile.vehicleType === 'ev' && profile.evLoanInterest < 150000,
      description: 'If you bought an electric vehicle with a loan, you can claim deduction on the interest paid under Section 80EEB up to ₹1,50,000 per year. This is over and above the standard 80C limit.',
      action: `Ensure your EV loan interest certificate is obtained from the lender. The unused limit is ₹${formatINR(Math.max(0, 150000 - profile.evLoanInterest))}. Claim in ITR under Part B — Schedule VI.`,
      reason: 'You own an EV and have unused 80EEB limit',
    },
    {
      id: 'vehicle-depreciation',
      title: 'Vehicle Depreciation Deduction',
      section: 'Section 32 — 15-30% of vehicle cost as business expense',
      saving: profile.vehiclePurchaseValue * 0.15 * marginalRate,
      difficulty: 'medium',
      applicable: profile.hasVehicle && profile.vehicleUsage === 'commercial' && isBusiness && profile.vehiclePurchaseValue > 0,
      description: 'Business owners can claim depreciation on vehicles used for business under Section 32. Cars get 15% depreciation; commercial vehicles (autorickshaws, taxis) get 30%. New vehicles bought after April 1 get full-year depreciation in the first year.',
      action: `Claim ₹${formatINR(Math.round(profile.vehiclePurchaseValue * 0.15))} depreciation (15% of ₹${formatINR(profile.vehiclePurchaseValue)}) in your P&L account this year. Keep vehicle registration + usage log as evidence.`,
    },
    {
      id: 'commercial-registration',
      title: 'Register Vehicle as Commercial',
      section: 'GST ITC + Income Tax Deduction',
      // No principled way to price this from profile data alone — actual
      // ITC recovery depends on the real business-use fraction, which isn't
      // captured here. The previous vehicleValue * 18% * 50% was a guess at
      // that fraction, not a computation.
      saving: null,
      difficulty: 'advanced',
      applicable: profile.hasVehicle && profile.vehicleUsage === 'personal' && isBusiness,
      description: 'If your vehicle is used substantially for business purposes, registering/using it commercially allows you to claim GST Input Tax Credit (ITC) on the purchase and operating costs. Personal-use vehicles are blocked from ITC under CGST rules, but business-use vehicles are not.',
      action: 'Consult your CA to evaluate mixed-use vehicle treatment. Keep a mileage log separating business vs personal trips. If business use > 50%, you may be eligible for partial ITC.',
    },
    {
      id: 'ev-switch',
      title: 'Switch to EV for Tax Benefits',
      section: 'Section 80EEB + Lower Operational Cost',
      saving: 150000 * marginalRate,
      difficulty: 'advanced',
      applicable: profile.hasVehicle && profile.vehicleType !== 'ev' && hasIncome,
      description: 'Buying an EV unlocks Section 80EEB deduction of up to ₹1,50,000 on loan interest. Additionally, EVs have zero GST on charging, lower servicing costs, and potential state-level subsidies (FAME II).',
      action: 'If considering a vehicle upgrade, compare post-tax cost of EV vs petrol/diesel. The ₹1,50,000 deduction can save you up to ₹45,000 in tax annually at the 30% bracket.',
    },
  ];

  // ── Property strategies ───────────────────────────────────────────────────
  const propertyStrategies: Strategy[] = [
    {
      id: 'home-loan-interest',
      title: 'Maximize Home Loan Interest (Section 24b)',
      section: 'Section 24b — up to ₹2,00,000',
      saving: Math.min(200000, Math.max(0, 200000 - profile.homeLoanInterest)) * marginalRate,
      difficulty: 'easy',
      applicable: profile.hasProperty && profile.propertyLoanOutstanding > 0 && profile.homeLoanInterest < 200000,
      description: 'Home loan interest on self-occupied property is deductible up to ₹2,00,000 under Section 24b in the old tax regime. For rented property, full interest is deductible with no limit.',
      action: `You have ₹${formatINR(Math.max(0, 200000 - profile.homeLoanInterest))} unused limit. Get an interest certificate from your bank for ${TAX_YEAR} and claim it in Schedule HP of ITR.`,
    },
    {
      id: 'home-loan-80EEA',
      title: 'First Home Buyer Extra Deduction (80EEA)',
      section: 'Section 80EEA — additional ₹1,50,000',
      saving: Math.min(150000, Math.max(0, 150000 - profile.homeLoanInterest80EEA)) * marginalRate,
      difficulty: 'easy',
      applicable: profile.hasProperty && profile.propertyPurchaseYear >= 2019 && profile.homeLoanInterest80EEA < 150000 && profile.propertyPurchaseCost <= 4500000,
      description: 'First-time home buyers with property value up to ₹45 lakh (stamp duty value) can claim an additional ₹1,50,000 deduction on home loan interest under Section 80EEA, over and above the ₹2L Section 24b limit.',
      action: `Claim additional ₹${formatINR(Math.max(0, 150000 - profile.homeLoanInterest80EEA))} deduction under 80EEA. Ensure the property was purchased after 1 April 2019 and you didn't own any other property on the date of sanction.`,
    },
    {
      id: 'joint-ownership',
      title: 'Joint Ownership Tax Splitting',
      section: 'Income Tax Act — split deductions between co-owners',
      saving: profile.homeLoanInterest * marginalRate * 0.5,
      difficulty: 'medium',
      applicable: profile.hasProperty && profile.propertyLoanOutstanding > 0 && (profile.maritalStatus === 'married'),
      description: 'If you buy a property jointly with your spouse or family member, each co-owner can separately claim deductions on their share. This effectively doubles the 80C (principal) and Section 24b (interest) limits. Each can claim up to ₹2L interest + ₹1.5L principal.',
      action: 'For future property purchase, consider joint ownership with spouse. Both must be co-borrowers in the loan for the tax benefits to apply. Consult a CA to restructure existing property if feasible.',
    },
    {
      id: 'ltcg-reinvestment',
      title: 'LTCG Reinvestment to Avoid Capital Gains Tax',
      section: 'Section 54 / 54EC — save up to 100% of LTCG tax',
      // 12.5% flat — the real FY 2026-27 rate for property LTCG (s.112, no
      // indexation for post-23-Jul-2024 acquisitions). The previous 20% was
      // the pre-reform rate. No annual exemption here — the ₹1,25,000
      // exemption is specific to equity/listed-asset LTCG (s.112A), not
      // property, so it isn't applied to this (property-only) strategy.
      saving: profile.capitalGainsLtcg * 0.125,
      difficulty: 'medium',
      applicable: profile.capitalGainsLtcg > 0,
      description: 'Long-term capital gains from property sale can be fully exempted by reinvesting in a new residential property (Section 54) within 2 years, or in NHAI/REC bonds (Section 54EC) within 6 months up to ₹50 lakh.',
      action: `You have LTCG of ₹${formatINR(profile.capitalGainsLtcg)}. Reinvest in a new property within 2 years or invest up to ₹50L in 54EC bonds within 6 months of the sale to avoid the 12.5% LTCG tax.`,
    },
    {
      id: 'huf-property',
      title: 'Transfer Property to HUF',
      section: 'HUF Tax Benefits — separate tax slab',
      // The actual saving depends on what income the HUF would earn and
      // its own slab position — a full second tax computation this app
      // doesn't have inputs for. The previous grossIncome * 5% was not
      // derived from any of that.
      saving: null,
      difficulty: 'advanced',
      applicable: hasIncome && !profile.isHUF && (profile.maritalStatus === 'married'),
      description: 'A Hindu Undivided Family (HUF) is a separate legal entity with its own PAN and full tax slabs. Income-generating assets transferred to an HUF are taxed in the HUF\'s hands, potentially at lower rates.',
      action: 'Consult a CA to form an HUF. You (Karta) can gift assets to the HUF. The HUF can earn rental income, interest, etc. with its own ₹1.5L 80C and ₹2.5L exemption limit, reducing your personal tax burden.',
    },
  ];

  // ── Business purchase strategies ──────────────────────────────────────────
  const purchaseStrategies: Strategy[] = [
    {
      id: 'business-laptop',
      title: 'Laptop / Phone as Business Expense',
      section: 'Section 37 — 100% business expense deduction',
      saving: 80000 * marginalRate,
      difficulty: 'easy',
      applicable: isBusiness,
      description: 'Laptops, smartphones, tablets, and peripherals used for business are 100% deductible as business expenses under Section 37(1). If partially personal, apportion the business fraction. For salaried employees, these can be reimbursed tax-free by the employer.',
      action: 'Ensure you maintain invoices for all technology purchases. If self-employed, deduct full cost in the year of purchase or claim depreciation (WDV method). If salaried, request your employer to reimburse tech costs through a tax-free reimbursement policy.',
    },
    {
      id: 'gst-itc',
      title: 'Claim GST Input Tax Credit',
      section: 'CGST Act Section 16 — recover 18% GST on B2B purchases',
      // ITC recovered depends on actual GST-bearing business spend, which
      // isn't tracked in this profile — grossIncome * 3% (the previous
      // figure) has no relationship to that.
      saving: null,
      difficulty: 'medium',
      applicable: isBusiness,
      description: 'GST-registered businesses can claim Input Tax Credit (ITC) on all business purchases — office supplies, equipment, software subscriptions, professional services. ITC is a rupee-for-rupee reduction in your GST liability, not just a deduction.',
      action: 'Ensure all vendor invoices include your GSTIN. Reconcile GSTR-2B monthly to maximise ITC claims. ITC is blocked only for personal-use items, motor vehicles for personal use, and food/beverages. Claim all ITC within the annual return deadline.',
    },
    {
      id: 'fy-timing',
      title: 'Time Purchases Before March 31',
      section: 'Section 32 Depreciation — Full Year Benefit',
      saving: 50000 * marginalRate,
      difficulty: 'easy',
      applicable: isBusiness,
      description: `Assets purchased before March 31 (end of financial year) are eligible for full-year depreciation in ${TAX_YEAR}. Assets purchased after March 31 would only get half the depreciation in the first year.`,
      action: `Review any planned equipment or asset purchases. If budget-ready, buy before ${FY_END_DATE} to claim full depreciation this year. This applies to machinery, computers, office furniture, and commercial vehicles.`,
    },
    {
      id: 'presumptive-taxation',
      title: 'Switch to Presumptive Taxation (44AD)',
      section: 'Section 44AD — 8% or 6% of turnover as deemed profit',
      // Only saves money if actual margin exceeds the 8%/6% deemed rate —
      // this profile doesn't record actual margin, so there's no honest
      // number to show. The previous formula assumed a specific 30% actual
      // margin, which is exactly the kind of unstated assumption a real
      // calculation can't make on the user's behalf.
      saving: null,
      difficulty: 'medium',
      applicable: isBusiness && profile.businessIncome > 0 && profile.businessIncome <= 20000000,
      description: 'Under Section 44AD, small businesses with turnover up to ₹2 crore can declare 8% of turnover (6% for digital payments) as profit without maintaining detailed books. This simplifies compliance and often reduces effective tax if actual margins are higher.',
      action: `Your current business income is ₹${formatINR(profile.businessIncome)}. Under 44AD, deemed profit would be ₹${formatINR(profile.businessIncome * 0.08)} (8%). If your actual margin is higher, this saves tax. Consult a CA to compare.`,
    },
  ];

  // ── General burden reduction ───────────────────────────────────────────────
  const generalStrategies: Strategy[] = [
    {
      id: 'regime-comparison',
      title: 'Optimize Your Tax Regime',
      section: 'New vs Old Regime — pick the lower tax',
      saving: Math.abs(
        (() => {
          const newT = calculateTax({ ...profile, taxRegime: 'new' });
          const oldT = calculateTax({ ...profile, taxRegime: 'old' });
          return newT.totalTax - oldT.totalTax;
        })()
      ),
      difficulty: 'easy',
      applicable: hasIncome,
      description: (() => {
        const newT = calculateTax({ ...profile, taxRegime: 'new' });
        const oldT = calculateTax({ ...profile, taxRegime: 'old' });
        const better = newT.totalTax < oldT.totalTax ? 'New Regime' : 'Old Regime';
        const saved = Math.abs(newT.totalTax - oldT.totalTax);
        return `Based on your profile, the ${better} saves you ₹${saved.toLocaleString('en-IN')} in tax. New Regime: ₹${newT.totalTax.toLocaleString('en-IN')} | Old Regime: ₹${oldT.totalTax.toLocaleString('en-IN')}. The new regime gives ₹75K standard deduction but removes 80C/D deductions.`;
      })(),
      action: (() => {
        const newT = calculateTax({ ...profile, taxRegime: 'new' });
        const oldT = calculateTax({ ...profile, taxRegime: 'old' });
        const better = newT.totalTax < oldT.totalTax ? 'new' : 'old';
        return `Switch to ${better === 'new' ? 'New' : 'Old'} Regime. Update your tax regime selection in your Profile page. Inform your employer via Form 10-IEA if switching from old to new. You can switch once per year for business income.`;
      })(),
    },
    {
      id: 'nps-employer',
      title: 'Maximize NPS Employer Contribution',
      section: 'Section 80CCD(2) — 10% of basic, OUTSIDE 80C limit',
      // Was always the full 10% of CTC regardless of what's already
      // contributed (double-counting anyone partway there), at a hardcoded
      // 30% rate regardless of actual bracket — now unused headroom at the
      // real marginal rate, matching every other headroom-based strategy.
      saving: Math.max(0, profile.salaryCtc * 0.10 - profile.npsEmployer) * marginalRate,
      difficulty: 'medium',
      applicable: isSalaried && profile.salaryCtc > 0 && profile.npsEmployer < profile.salaryCtc * 0.10,
      description: 'Employer contribution to NPS (up to 10% of basic salary) is deductible under 80CCD(2) — this is COMPLETELY SEPARATE from the ₹1.5L Section 80C limit and the ₹50K Section 80CCD(1B) limit. This is one of the most underutilised tax deductions for salaried employees.',
      action: `Ask your HR/employer to redirect some of your CTC into NPS employer contribution. Up to ₹${formatINR(Math.round(profile.salaryCtc * 0.10))} (10% of your ₹${formatINR(profile.salaryCtc)} CTC) can be deducted tax-free, with zero impact on your 80C investments.`,
    },
    {
      id: 'salary-restructure',
      title: 'Salary Restructuring — Add Tax-Free Components',
      section: 'Multiple exemptions — HRA, LTA, food coupons, car allowance',
      // Depends on how much of the CTC the employer is willing to move into
      // exempt components, which varies by employer — salaryCtc * 5% (the
      // previous figure) was not derived from any actual exemption amount.
      saving: null,
      difficulty: 'medium',
      applicable: isSalaried && profile.salaryCtc > 0 && (profile.hra < profile.salaryCtc * 0.20),
      description: 'Optimally restructuring your salary can save 5-10% in taxes by replacing taxable salary with tax-exempt allowances: HRA (up to 50% of basic in metros), LTA (₹20-50K), food coupons (₹26,400/year), internet reimbursement, car allowance for official use.',
      action: 'Request your HR to review your CTC structure. Key components to add: HRA (if you pay rent), LTA (claim twice in a 4-year block), meal vouchers (₹2,200/month exempt), books/periodicals allowance, car+fuel reimbursement for business travel.',
    },
    {
      id: 'advance-tax',
      title: 'Pay Advance Tax — Avoid 234B/234C Interest',
      section: 'Section 234B/234C — save 12% p.a. interest',
      // Real 234B/234C interest depends on which instalments are missed and
      // by how many months — a flat 6% of total tax (the previous figure)
      // doesn't reflect any specific payment timeline. The instalment
      // schedule below is real; only the headline saving was a guess.
      saving: null,
      difficulty: 'easy',
      applicable: hasIncome && tax.totalTax > 10000,
      description: 'If your total tax liability exceeds ₹10,000, you must pay Advance Tax in 4 instalments (Jun 15: 15%, Sep 15: 45%, Dec 15: 75%, Mar 15: 100%). Missing these attracts 1% per month (12% p.a.) interest under 234B/234C.',
      action: `Your estimated tax is ₹${formatINR(tax.totalTax)}. Schedule advance tax payments: Jun 15 (₹${formatINR(tax.totalTax * 0.15)}), Sep 15 (₹${formatINR(tax.totalTax * 0.30)}), Dec 15 (₹${formatINR(tax.totalTax * 0.30)}), Mar 15 (₹${formatINR(tax.totalTax * 0.25)}). Use the income tax portal challan 280.`,
    },
    {
      id: '80d-maximize',
      title: 'Maximize Health Insurance Deductions',
      section: 'Section 80D — ₹25K self + ₹25K-50K parents',
      saving: (Math.max(0, 25000 - profile.healthInsuranceSelf) + Math.max(0, (profile.seniorParents ? 50000 : 25000) - profile.healthInsuranceParents)) * marginalRate,
      difficulty: 'easy',
      applicable: (profile.healthInsuranceSelf < 25000 || profile.healthInsuranceParents < (profile.seniorParents ? 50000 : 25000)),
      description: 'Section 80D allows deduction for health insurance premiums: ₹25,000 for self/spouse/children, and ₹25,000 (or ₹50,000 if parents are senior citizens 60+) for parents. Prevention health check-ups up to ₹5,000 are also included within this limit.',
      action: `You have unused 80D limit of ₹${formatINR(Math.max(0, 25000 - profile.healthInsuranceSelf))} (self) + ₹${formatINR(Math.max(0, (profile.seniorParents ? 50000 : 25000) - profile.healthInsuranceParents))} (parents). Buy/upgrade health insurance before ${FY_END_DATE}. Prefer annual policies for full-year coverage and maximum deduction.`,
    },
    {
      id: '80ccd-nps',
      title: 'Extra NPS Investment (80CCD(1B))',
      section: 'Section 80CCD(1B) — additional ₹50,000 over 80C',
      saving: Math.max(0, 50000 - profile.npsEmployee) * marginalRate,
      difficulty: 'easy',
      applicable: profile.npsEmployee < 50000 && hasIncome,
      description: 'NPS Tier-I investment up to ₹50,000 is deductible under Section 80CCD(1B), which is completely outside the ₹1.5L Section 80C limit. This gives an additional ₹50K deduction on top of your 80C investments, potentially saving up to ₹15,600 in taxes at the 30% bracket.',
      action: `You have ₹${formatINR(Math.max(0, 50000 - profile.npsEmployee))} unused NPS limit. Open NPS Tier-I account at any bank or NSDL website. Invest before ${FY_END_DATE}. Note: 60% is tax-free on maturity (60 years), remaining 40% must be used to buy annuity.`,
    },
  ];

  const totalVehicleSavings = vehicleStrategies.filter((s) => s.applicable).reduce((a, s) => a + (s.saving ?? 0), 0);
  const totalPropertySavings = propertyStrategies.filter((s) => s.applicable).reduce((a, s) => a + (s.saving ?? 0), 0);
  const totalPurchaseSavings = purchaseStrategies.filter((s) => s.applicable).reduce((a, s) => a + (s.saving ?? 0), 0);
  const totalGeneralSavings = generalStrategies.filter((s) => s.applicable).reduce((a, s) => a + (s.saving ?? 0), 0);
  const grandTotal = totalVehicleSavings + totalPropertySavings + totalPurchaseSavings + totalGeneralSavings;

  const [activeTab, setActiveTab] = useState<'strategies' | 'advisor'>('strategies');

  return (
    <AppLayout title="Smart Savings" subtitle={`Real-time cost reduction + AI Purchase Advisor · ${TAX_YEAR}`}>

      {/* Tab bar */}
      <div className="flex items-center gap-1 p-1 mb-5 rounded-xl bg-white border border-line w-fit shadow-sm">
        {[
          { id: 'strategies', label: 'Strategies', icon: LayoutGrid },
          { id: 'advisor', label: 'Purchase Advisor', icon: MessageCircle, badge: 'AI' },
        ].map(({ id, label, icon: Icon, badge }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id as 'strategies' | 'advisor')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-[13px] font-semibold transition-all duration-200 ${
              activeTab === id
                ? 'bg-primary text-white shadow-md shadow-primary/25'
                : 'text-ink-soft hover:text-ink hover:bg-paper'
            }`}
          >
            <Icon size={14} />
            {label}
            {badge && (
              <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-md ${
                activeTab === id ? 'bg-white/20 text-white' : 'bg-saffron/15 text-saffron'
              }`}>{badge}</span>
            )}
          </button>
        ))}
      </div>

      {/* Purchase Advisor tab */}
      {activeTab === 'advisor' && (
        <div className="animate-rise">
          <PurchaseAdvisorChat />
        </div>
      )}

      {/* Strategies tab */}
      {activeTab === 'strategies' && <>

      {/* Profile incomplete warning */}
      {completeness < 40 && (
        <div className="flex items-start gap-3 p-4 mb-5 rounded-xl bg-saffron/10 border border-saffron/25">
          <AlertTriangle size={16} className="text-saffron mt-0.5 shrink-0" />
          <div>
            <p className="text-[13.5px] font-semibold text-ink">Profile is only {completeness}% complete</p>
            <p className="text-[12.5px] text-ink-soft mt-0.5">
              More strategies unlock as you fill in your income, assets, and investments.{' '}
              <Link to="/profile" className="text-primary font-semibold underline">Complete Profile →</Link>
            </p>
          </div>
        </div>
      )}

      {/* Hero banner */}
      <div className="rounded-2xl bg-gradient-to-br from-navy to-navy-deep text-white p-6 mb-5 relative overflow-hidden">
        <div className="absolute -right-10 -top-10 w-56 h-56 rounded-full bg-gradient-to-br from-saffron/20 to-teal/10 blur-2xl" />
        <div className="relative">
          <div className="flex items-center gap-2 mb-3">
            <Zap size={18} className="text-saffron" />
            <p className="text-[11px] font-semibold uppercase tracking-wide text-white/60">AI-Powered · Personalised to your profile</p>
          </div>
          <p className="font-display font-bold text-[28px] leading-tight mb-1">
            {formatINR(Math.round(grandTotal))}
          </p>
          <p className="text-[13px] text-white/60">estimated annual savings across {[vehicleStrategies, propertyStrategies, purchaseStrategies, generalStrategies].flat().filter((s) => s.applicable).length} strategies</p>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-5 pt-5 border-t border-white/10">
            {[
              { label: 'Vehicle', icon: Car, value: totalVehicleSavings },
              { label: 'Property', icon: Home, value: totalPropertySavings },
              { label: 'Purchases', icon: ShoppingBag, value: totalPurchaseSavings },
              { label: 'General', icon: Wallet, value: totalGeneralSavings },
            ].map(({ label, icon: Icon, value }) => (
              <div key={label}>
                <div className="flex items-center gap-1.5 mb-0.5">
                  <Icon size={12} className="text-white/50" />
                  <p className="text-[10.5px] text-white/50">{label}</p>
                </div>
                <p className="ledger-num text-[14px] font-bold text-saffron-light">{formatINR(Math.round(value))}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Regime comparison strip */}
      {hasIncome && (() => {
        const newT = calculateTax({ ...profile, taxRegime: 'new' });
        const oldT = calculateTax({ ...profile, taxRegime: 'old' });
        const better = newT.totalTax < oldT.totalTax ? 'New Regime' : 'Old Regime';
        const saved = Math.abs(newT.totalTax - oldT.totalTax);
        return (
          <div className="flex items-center gap-3 p-4 mb-5 rounded-xl border border-primary/20 bg-primary/5">
            <BarChart3 size={16} className="text-primary shrink-0" />
            <div className="flex-1">
              <p className="text-[13px] font-semibold text-ink">
                <span className="text-primary">{better}</span> saves you {formatINR(saved)} vs the other regime
              </p>
              <p className="text-[11.5px] text-ink-soft">
                New: {formatINR(newT.totalTax)} &nbsp;|&nbsp; Old: {formatINR(oldT.totalTax)}
              </p>
            </div>
            <Link to="/profile" className="text-[12px] font-semibold text-primary flex items-center gap-1 whitespace-nowrap">
              Change <ChevronRight size={13} />
            </Link>
          </div>
        );
      })()}

      {/* Strategy categories */}
      <div className="space-y-4 stagger">
        <Category
          icon={Car} title="Vehicle Cost Reduction" color="bg-saffron/10 text-saffron"
          strategies={vehicleStrategies} totalSaving={totalVehicleSavings}
        />
        <Category
          icon={Home} title="Property & Real Estate" color="bg-teal/10 text-teal"
          strategies={propertyStrategies} totalSaving={totalPropertySavings}
        />
        <Category
          icon={ShoppingBag} title="Business Purchases & Products" color="bg-primary/10 text-primary"
          strategies={purchaseStrategies} totalSaving={totalPurchaseSavings}
        />
        <Category
          icon={Wallet} title="General Tax Burden Reduction" color="bg-navy/10 text-navy"
          strategies={generalStrategies} totalSaving={totalGeneralSavings}
        />
      </div>

      {/* No strategies */}
      {grandTotal === 0 && completeness > 40 && (
        <Card className="p-8 text-center">
          <div className="w-12 h-12 rounded-2xl bg-teal/10 text-teal flex items-center justify-center mx-auto mb-3">
            <CheckCircle size={22} />
          </div>
          <p className="font-semibold text-ink text-[15px] mb-1">You're well optimized!</p>
          <p className="text-[13px] text-ink-soft">No major missed strategies found based on your current profile. Keep it up.</p>
        </Card>
      )}

      {/* Disclaimer */}
      <div className="flex items-start gap-2 p-3 rounded-xl bg-paper border border-line mt-5">
        <Info size={13} className="text-ink-soft mt-0.5 shrink-0" />
        <p className="text-[11px] text-ink-soft leading-relaxed">
          Savings estimates are illustrative and based on your profile data + {TAX_YEAR} tax rules. Strategies marked "Depends on your situation" have no reliable rupee estimate from profile data alone. Actual results may vary. Always consult a Chartered Accountant before making financial decisions.
        </p>
      </div>
      </>}
    </AppLayout>
  );
}
