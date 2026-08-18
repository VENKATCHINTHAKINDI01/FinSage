/**
 * useProfileStore — Complete Financial Profile
 * Persisted to localStorage. Powers all AI context and personalized suggestions.
 *
 * `calculateTax()` below is an ESTIMATE, not the source of truth. It exists
 * so a form can show instant feedback while someone is typing, before a
 * round trip to POST /api/v1/compliance/calculator completes. Once that
 * response is back, it is what gets shown as the user's actual figure —
 * backend.core is the only place a filing-grade number comes from, the same
 * rule this product applies everywhere else. Any UI displaying a value from
 * this function should label it "estimate" and defer to the API result
 * where one exists.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { getProfile, updateProfile as apiUpdateProfile } from '../api/services';

export type Profession =
  | 'salaried'
  | 'business_owner'
  | 'freelancer'
  | 'professional'    // CA / Doctor / Lawyer / Architect
  | 'retired'
  | 'student'
  | '';

export type TaxRegime = 'new' | 'old';
export type ResidentialStatus = 'resident' | 'nri' | 'rnor';

export interface FinancialProfile {
  // ── Personal ────────────────────────────────────────────
  dob: string;                    // ISO date string
  pan: string;
  aadhaarLast4: string;
  state: string;
  residentialStatus: ResidentialStatus;

  // ── Profession ──────────────────────────────────────────
  profession: Profession;
  employerName: string;
  businessType: string;          // for business owners

  // ── Income (annual, INR) ─────────────────────────────────
  salaryCtc: number;
  salaryInHand: number;
  businessIncome: number;
  freelanceIncome: number;
  rentalIncome: number;
  capitalGainsStcg: number;
  capitalGainsLtcg: number;
  otherIncome: number;
  dividendIncome: number;

  // ── Investments ──────────────────────────────────────────
  ppf: number;
  elss: number;
  npsEmployee: number;           // 80CCD(1B) — extra ₹50K
  npsEmployer: number;           // 80CCD(2) — % of basic by employer
  lic: number;
  ulip: number;
  fd5yr: number;                 // 5-year tax-saver FD
  sukanyaSamriddhi: number;
  nsc: number;
  homeLoanPrincipal: number;     // 80C component

  // ── Deductions (80 series) ───────────────────────────────
  healthInsuranceSelf: number;   // 80D
  healthInsuranceParents: number; // 80D — extra ₹25K/50K for senior parents
  eduLoanInterest: number;       // 80E
  homeLoanInterest: number;      // Sec 24b — ₹2L limit
  homeLoanInterest80EEA: number; // extra ₹1.5L for first-time buyers
  evLoanInterest: number;        // 80EEB — ₹1.5L
  savingsBankInterest: number;   // 80TTA — ₹10K
  donationsU80G: number;
  hra: number;                   // HRA exemption claimed
  lta: number;                   // LTA exemption

  // ── Assets ───────────────────────────────────────────────
  hasProperty: boolean;
  propertyType: 'self_occupied' | 'rented' | 'vacant' | '';
  propertyPurchaseCost: number;
  propertyPurchaseYear: number;
  propertyLoanOutstanding: number;
  hasVehicle: boolean;
  vehicleType: 'two_wheeler' | 'car' | 'ev' | '';
  vehicleUsage: 'personal' | 'commercial' | '';
  vehiclePurchaseValue: number;
  goldValue: number;
  equityPortfolioValue: number;
  mutualFundValue: number;

  // ── Tax Preference ───────────────────────────────────────
  taxRegime: TaxRegime;
  isHUF: boolean;
  filingStatus: 'individual' | 'huf';

  // ── Family ───────────────────────────────────────────────
  maritalStatus: 'single' | 'married' | 'widowed' | '';
  dependents: number;
  seniorParents: boolean;        // parents 60+ → higher 80D limit
  superSeniorParents: boolean;   // parents 80+ → ₹50K 80D limit
}

const DEFAULT_PROFILE: FinancialProfile = {
  dob: '',
  pan: '',
  aadhaarLast4: '',
  state: '',
  residentialStatus: 'resident',

  profession: '',
  employerName: '',
  businessType: '',

  salaryCtc: 0,
  salaryInHand: 0,
  businessIncome: 0,
  freelanceIncome: 0,
  rentalIncome: 0,
  capitalGainsStcg: 0,
  capitalGainsLtcg: 0,
  otherIncome: 0,
  dividendIncome: 0,

  ppf: 0,
  elss: 0,
  npsEmployee: 0,
  npsEmployer: 0,
  lic: 0,
  ulip: 0,
  fd5yr: 0,
  sukanyaSamriddhi: 0,
  nsc: 0,
  homeLoanPrincipal: 0,

  healthInsuranceSelf: 0,
  healthInsuranceParents: 0,
  eduLoanInterest: 0,
  homeLoanInterest: 0,
  homeLoanInterest80EEA: 0,
  evLoanInterest: 0,
  savingsBankInterest: 0,
  donationsU80G: 0,
  hra: 0,
  lta: 0,

  hasProperty: false,
  propertyType: '',
  propertyPurchaseCost: 0,
  propertyPurchaseYear: 0,
  propertyLoanOutstanding: 0,
  hasVehicle: false,
  vehicleType: '',
  vehicleUsage: '',
  vehiclePurchaseValue: 0,
  goldValue: 0,
  equityPortfolioValue: 0,
  mutualFundValue: 0,

  taxRegime: 'new',
  isHUF: false,
  filingStatus: 'individual',

  maritalStatus: '',
  dependents: 0,
  seniorParents: false,
  superSeniorParents: false,
};

// ── Tax constants, FY 2026-27 ────────────────────────────────────────────────
//
// This is a client-side ESTIMATE only — see the module docstring below.
// Every figure a user relies on to file comes from POST /api/v1/compliance/
// calculator (backend.core, versioned rule packs, golden-tested). These
// constants exist so a form can show instant feedback while someone is
// typing, before that round trip completes.

export const TAX_YEAR = 'FY 2026–27';
export const ASSESSMENT_YEAR = 'AY 2027–28';
export const ITR_DEADLINE = '31 Jul 2027';
// ISO form for date arithmetic — the display string above is not reliably
// parseable by `new Date(...)` across engines.
export const ITR_DEADLINE_ISO = '2027-07-31';
export const FY_END_DATE = '31 March 2027';

export const NEW_REGIME_SLABS = [
  { min: 0, max: 400000, rate: 0 },
  { min: 400000, max: 800000, rate: 0.05 },
  { min: 800000, max: 1200000, rate: 0.10 },
  { min: 1200000, max: 1600000, rate: 0.15 },
  { min: 1600000, max: 2000000, rate: 0.20 },
  { min: 2000000, max: 2400000, rate: 0.25 },
  { min: 2400000, max: Infinity, rate: 0.30 },
];

export const OLD_REGIME_SLABS = [
  { min: 0, max: 250000, rate: 0 },
  { min: 250000, max: 500000, rate: 0.05 },
  { min: 500000, max: 1000000, rate: 0.20 },
  { min: 1000000, max: Infinity, rate: 0.30 },
];

export const STD_DEDUCTION_NEW = 75000;
export const STD_DEDUCTION_OLD = 50000;
export const CESS_RATE = 0.04;
export const REBATE_87A_THRESHOLD_NEW = 1200000;
export const REBATE_87A_THRESHOLD_OLD = 500000;
export const SECTION_80C_LIMIT = 150000;
export const SECTION_80D_SELF_LIMIT = 25000;
export const SECTION_80D_PARENTS_LIMIT = 25000;
export const SECTION_80D_SENIOR_PARENTS_LIMIT = 50000;
export const SECTION_80CCD_1B_LIMIT = 50000;
export const SECTION_24B_LIMIT = 200000;
export const SECTION_80EEA_LIMIT = 150000;
export const SECTION_80EEB_LIMIT = 150000;

// ── Tax calculator ───────────────────────────────────────────────────────────

function calcSlabTax(taxable: number, slabs: typeof NEW_REGIME_SLABS): number {
  let tax = 0;
  for (const { min, max, rate } of slabs) {
    if (taxable <= min) break;
    tax += (Math.min(taxable, max) - min) * rate;
  }
  return tax;
}

/**
 * The slab rate that applies to the NEXT rupee of income — real marginal
 * benefit of a deduction depends on this, not a flat assumed bracket.
 * Still an approximation: it does not account for crossing the 87A rebate
 * or surcharge boundary, where the true marginal rate briefly spikes far
 * above any slab rate (see `calculateTax`'s marginal-relief note). Good
 * enough for an instant "roughly this much" while a form is being filled;
 * never the number a filing decision should rest on.
 */
export function marginalRateAt(taxable: number, regime: TaxRegime): number {
  const slabs = regime === 'new' ? NEW_REGIME_SLABS : OLD_REGIME_SLABS;
  for (let i = slabs.length - 1; i >= 0; i--) {
    if (taxable > slabs[i].min) return slabs[i].rate;
  }
  return 0;
}

export function calculateTax(profile: FinancialProfile): {
  grossIncome: number;
  totalDeductions: number;
  taxableIncome: number;
  incomeTax: number;
  cess: number;
  totalTax: number;
  effectiveRate: number;
  potentialSavings: number;
  regime: TaxRegime;
} {
  const gross =
    (profile.profession === 'salaried' ? profile.salaryCtc : 0) +
    profile.businessIncome +
    profile.freelanceIncome +
    profile.rentalIncome +
    profile.capitalGainsStcg +
    profile.capitalGainsLtcg +
    profile.otherIncome +
    profile.dividendIncome;

  const sec80C = Math.min(
    profile.ppf + profile.elss + profile.lic + profile.ulip +
    profile.fd5yr + profile.sukanyaSamriddhi + profile.nsc +
    profile.homeLoanPrincipal,
    SECTION_80C_LIMIT
  );

  const sec80D = Math.min(
    profile.healthInsuranceSelf,
    SECTION_80D_SELF_LIMIT
  ) + Math.min(
    profile.healthInsuranceParents,
    profile.superSeniorParents
      ? SECTION_80D_SENIOR_PARENTS_LIMIT
      : profile.seniorParents
        ? SECTION_80D_SENIOR_PARENTS_LIMIT
        : SECTION_80D_PARENTS_LIMIT
  );

  const sec24b = Math.min(profile.homeLoanInterest, SECTION_24B_LIMIT);
  const sec80EEA = Math.min(profile.homeLoanInterest80EEA, SECTION_80EEA_LIMIT);
  const sec80EEB = Math.min(profile.evLoanInterest, SECTION_80EEB_LIMIT);
  const sec80CCD1B = Math.min(profile.npsEmployee, SECTION_80CCD_1B_LIMIT);
  const sec80E = profile.eduLoanInterest;
  const sec80G = profile.donationsU80G;
  const sec80TTA = Math.min(profile.savingsBankInterest, 10000);
  const hra = profile.hra;
  const lta = profile.lta;

  const stdDed = profile.taxRegime === 'new' ? STD_DEDUCTION_NEW : STD_DEDUCTION_OLD;

  const totalDeductionsOld =
    stdDed + sec80C + sec80CCD1B + sec80D + sec24b + sec80EEA +
    sec80EEB + sec80E + sec80G + sec80TTA + hra + lta;
  const totalDeductionsNew = stdDed;

  const totalDed = profile.taxRegime === 'old' ? totalDeductionsOld : totalDeductionsNew;
  const taxable = Math.max(0, gross - totalDed);

  const slabs = profile.taxRegime === 'new' ? NEW_REGIME_SLABS : OLD_REGIME_SLABS;
  let incomeTax = calcSlabTax(taxable, slabs);

  // s.87A rebate, WITH marginal relief. A flat threshold ("nil below ₹12L,
  // full slab tax from ₹12,00,001") is a cliff bug: it would tax someone
  // earning ten rupees more than the threshold ₹60,001.50, not ₹10. Marginal
  // relief caps the tax at the excess income over the threshold, so it rises
  // by at most the rupee that crossed the line.
  const rebateThreshold = profile.taxRegime === 'new' ? REBATE_87A_THRESHOLD_NEW : REBATE_87A_THRESHOLD_OLD;
  if (taxable <= rebateThreshold) {
    incomeTax = 0;
  } else {
    incomeTax = Math.min(incomeTax, taxable - rebateThreshold);
  }

  const cess = incomeTax * CESS_RATE;
  const total = incomeTax + cess;
  const effectiveRate = gross > 0 ? (total / gross) * 100 : 0;

  // Potential savings = unused deduction headroom valued at the REAL marginal
  // rate at this income, not a flat assumed bracket — the flat-rate version
  // of this overstated savings for anyone below the top slab and understated
  // it for anyone in it.
  const marginalRate = marginalRateAt(taxable, profile.taxRegime);
  const maxPossible80C = SECTION_80C_LIMIT;
  const maxPossible80D = SECTION_80D_SELF_LIMIT + (profile.seniorParents ? SECTION_80D_SENIOR_PARENTS_LIMIT : SECTION_80D_PARENTS_LIMIT);
  const unusedSavings = Math.max(0,
    (maxPossible80C - sec80C) * marginalRate +
    (maxPossible80D - sec80D) * marginalRate +
    (SECTION_80CCD_1B_LIMIT - sec80CCD1B) * marginalRate
  );

  return {
    grossIncome: gross,
    totalDeductions: totalDed,
    taxableIncome: taxable,
    incomeTax,
    cess,
    totalTax: total,
    effectiveRate,
    potentialSavings: unusedSavings,
    regime: profile.taxRegime,
  };
}

// ── Profile completeness ─────────────────────────────────────────────────────

export function profileCompleteness(p: FinancialProfile): number {
  const checks = [
    !!p.dob,
    !!p.state,
    !!p.profession,
    p.salaryCtc > 0 || p.businessIncome > 0 || p.freelanceIncome > 0,
    p.ppf > 0 || p.elss > 0 || p.lic > 0 || p.npsEmployee > 0,
    p.healthInsuranceSelf > 0,
    !!p.maritalStatus,
    !!p.taxRegime,
    p.homeLoanInterest > 0 || !p.hasProperty,
    p.vehicleType !== '' || !p.hasVehicle,
  ];
  return Math.round((checks.filter(Boolean).length / checks.length) * 100);
}

// ── AI context builder ───────────────────────────────────────────────────────

export function buildAIContext(p: FinancialProfile): string {
  const tax = calculateTax(p);
  return `
User Financial Profile (FY 2025-26):
- Profession: ${p.profession || 'not specified'}
- State: ${p.state || 'not specified'}  
- Residential Status: ${p.residentialStatus}
- Tax Regime: ${p.taxRegime} regime
- Gross Income: ₹${tax.grossIncome.toLocaleString('en-IN')}
  - Salary: ₹${p.salaryCtc.toLocaleString('en-IN')}
  - Business: ₹${p.businessIncome.toLocaleString('en-IN')}
  - Rental: ₹${p.rentalIncome.toLocaleString('en-IN')}
  - Capital Gains (STCG): ₹${p.capitalGainsStcg.toLocaleString('en-IN')}
  - Capital Gains (LTCG): ₹${p.capitalGainsLtcg.toLocaleString('en-IN')}
- Total Deductions: ₹${tax.totalDeductions.toLocaleString('en-IN')}
- Taxable Income: ₹${tax.taxableIncome.toLocaleString('en-IN')}
- Estimated Tax: ₹${tax.totalTax.toLocaleString('en-IN')} (${tax.effectiveRate.toFixed(1)}% effective)
- Investments: PPF ₹${p.ppf.toLocaleString('en-IN')}, ELSS ₹${p.elss.toLocaleString('en-IN')}, NPS ₹${p.npsEmployee.toLocaleString('en-IN')}
- Health Insurance: Self ₹${p.healthInsuranceSelf.toLocaleString('en-IN')}, Parents ₹${p.healthInsuranceParents.toLocaleString('en-IN')}
- Home Loan Interest: ₹${p.homeLoanInterest.toLocaleString('en-IN')}
- Has Property: ${p.hasProperty ? p.propertyType : 'No'}
- Has Vehicle: ${p.hasVehicle ? `${p.vehicleType} (${p.vehicleUsage})` : 'No'}
- Family: ${p.maritalStatus}, ${p.dependents} dependents, Senior parents: ${p.seniorParents}
- Potential additional savings: ~₹${tax.potentialSavings.toLocaleString('en-IN')}
`.trim();
}

// ── Store ────────────────────────────────────────────────────────────────────

interface ProfileState {
  profile: FinancialProfile;
  isProfileComplete: boolean;
  completeness: number;
  updateProfile: (partial: Partial<FinancialProfile>) => void;
  resetProfile: () => void;
  fetchProfile: () => Promise<void>;
  saveProfile: (p: FinancialProfile) => Promise<void>;
}

export const useProfileStore = create<ProfileState>()(
  persist(
    (set) => ({
      profile: DEFAULT_PROFILE,
      isProfileComplete: false,
      completeness: 0,

      updateProfile: (partial) =>
        set((state) => {
          const updated = { ...state.profile, ...partial };
          const pct = profileCompleteness(updated);
          return {
            profile: updated,
            completeness: pct,
            isProfileComplete: pct >= 60,
          };
        }),

      resetProfile: () =>
        set({ profile: DEFAULT_PROFILE, isProfileComplete: false, completeness: 0 }),

      fetchProfile: async () => {
        try {
          const res = await getProfile();
          if (res && res.success && res.profile) {
            const pct = profileCompleteness(res.profile);
            set({
              profile: res.profile,
              completeness: pct,
              isProfileComplete: pct >= 60,
            });
          }
        } catch (err) {
          console.error("Failed to fetch profile from backend:", err);
        }
      },

      saveProfile: async (p: FinancialProfile) => {
        const pct = profileCompleteness(p);
        set({
          profile: p,
          completeness: pct,
          isProfileComplete: pct >= 60,
        });
        try {
          await apiUpdateProfile(p);
        } catch (err) {
          console.error("Failed to save profile to backend:", err);
        }
      },
    }),
    { name: 'finsage_profile' }
  )
);
