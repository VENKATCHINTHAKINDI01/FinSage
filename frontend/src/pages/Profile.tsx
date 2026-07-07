import { useState, useEffect } from 'react';
import AppLayout from '../components/shared/AppLayout';
import { Card, Badge } from '../components/ui/Primitives';
import { useAuthStore } from '../store/useAuthStore';
import { useProfileStore, profileCompleteness, calculateTax, TAX_YEAR } from '../store/useProfileStore';
import type { FinancialProfile } from '../store/useProfileStore';
import { formatINR } from '../utils/format';
import {
  LogOut, CheckCircle, User, Briefcase,
  PiggyBank, Home, Shield, ChevronRight, ChevronDown,
  ShieldCheck, AlertTriangle, Info, Zap, BarChart3,
} from 'lucide-react';

// ── Helpers ──────────────────────────────────────────────────────────────────

const INDIAN_STATES = [
  'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chhattisgarh',
  'Goa', 'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jharkhand', 'Karnataka',
  'Kerala', 'Madhya Pradesh', 'Maharashtra', 'Manipur', 'Meghalaya', 'Mizoram',
  'Nagaland', 'Odisha', 'Punjab', 'Rajasthan', 'Sikkim', 'Tamil Nadu',
  'Telangana', 'Tripura', 'Uttar Pradesh', 'Uttarakhand', 'West Bengal',
  'Delhi', 'Jammu & Kashmir', 'Ladakh', 'Puducherry', 'Chandigarh',
];

function inp(
  label: string,
  value: number | string,
  onChange: (v: any) => void,
  opts: { type?: string; placeholder?: string; prefix?: string; max?: number; step?: number } = {}
) {
  const isNum = opts.type === 'number' || typeof value === 'number';
  return (
    <div>
      <label className="block text-[12px] font-medium text-ink-soft mb-1">{label}</label>
      <div className="relative">
        {opts.prefix && (
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[13px] text-ink-soft font-medium">{opts.prefix}</span>
        )}
        <input
          type={isNum ? 'number' : 'text'}
          value={value}
          min={0}
          max={opts.max}
          step={opts.step || (isNum ? 1000 : undefined)}
          placeholder={opts.placeholder || '0'}
          onChange={(e) => onChange(isNum ? Number(e.target.value) : e.target.value)}
          className={`w-full h-9 rounded-lg border border-line bg-paper text-ink text-[13.5px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition ${opts.prefix ? 'pl-7' : 'px-3'} pr-3`}
        />
      </div>
    </div>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function sel(label: string, value: string, onChange: (v: any) => void, options: { value: string; label: string }[]) {
  return (
    <div>
      <label className="block text-[12px] font-medium text-ink-soft mb-1">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full h-9 rounded-lg border border-line bg-paper text-ink text-[13.5px] px-3 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition"
      >
        <option value="">— Select —</option>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}

function tog(label: string, value: boolean, onChange: (v: boolean) => void) {
  return (
    <label className="flex items-center gap-3 cursor-pointer select-none">
      <button
        type="button"
        onClick={() => onChange(!value)}
        className={`w-10 h-5 rounded-full transition-colors relative shrink-0 ${value ? 'bg-primary' : 'bg-line'}`}
      >
        <span className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${value ? 'translate-x-5' : 'translate-x-0'}`} />
      </button>
      <span className="text-[13.5px] text-ink">{label}</span>
    </label>
  );
}

// ── Section component ────────────────────────────────────────────────────────

function Section({
  icon: Icon, title, eyebrow, isOpen, onToggle, onSave, children,
}: {
  icon: any; title: string; eyebrow: string; isOpen: boolean;
  onToggle: () => void; onSave: () => void; isEditing?: boolean; children: React.ReactNode;
}) {
  return (
    <Card className="overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between p-5 hover:bg-paper/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0">
            <Icon size={16} />
          </div>
          <div className="text-left">
            <p className="text-[10.5px] font-semibold uppercase tracking-wide text-ink-soft">{eyebrow}</p>
            <p className="text-[14px] font-semibold text-ink">{title}</p>
          </div>
        </div>
        {isOpen ? <ChevronDown size={16} className="text-ink-soft" /> : <ChevronRight size={16} className="text-ink-soft" />}
      </button>

      {isOpen && (
        <div className="px-5 pb-5 border-t border-line">
          <div className="pt-5 space-y-4">{children}</div>
          <div className="flex gap-3 mt-5">
            <button
              onClick={onSave}
              className="h-9 px-5 rounded-lg bg-primary text-white text-[13px] font-semibold hover:bg-primary/90 transition-colors flex items-center gap-2"
            >
              <CheckCircle size={14} /> Save changes
            </button>
          </div>
        </div>
      )}
    </Card>
  );
}

// ── Main component ───────────────────────────────────────────────────────────

export default function Profile() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const { profile, fetchProfile, saveProfile } = useProfileStore();

  // Local draft state for editing
  const [draft, setDraft] = useState<FinancialProfile>(profile);
  const [openSection, setOpenSection] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    fetchProfile();
  }, [fetchProfile]);

  useEffect(() => {
    setDraft(profile);
  }, [profile]);

  const completeness = profileCompleteness(profile);
  const tax = calculateTax(profile);

  const name = user?.name || 'User';
  const email = user?.email || '';
  const initials = name.split(' ').map((n: string) => n[0]).slice(0, 2).join('').toUpperCase();

  function toggle(section: string) {
    setDraft(profile); // reset draft to current saved values
    setOpenSection(openSection === section ? null : section);
  }

  function save(section: string) {
    saveProfile(draft);
    setSaved(section);
    setTimeout(() => setSaved(null), 2500);
    setOpenSection(null);
  }

  function set<K extends keyof FinancialProfile>(field: K) {
    return (v: FinancialProfile[K]) => setDraft((d) => ({ ...d, [field]: v }));
  }

  const completenessColor = completeness >= 80 ? 'text-teal' : completeness >= 50 ? 'text-saffron' : 'text-danger';
  const completenessRing = completeness >= 80 ? 'bg-teal' : completeness >= 50 ? 'bg-saffron' : 'bg-danger';

  return (
    <AppLayout title="Financial Profile" subtitle={`${TAX_YEAR} · Personalise your advisor`}>
      {saved && (
        <div className="fixed top-5 right-5 z-50 flex items-center gap-2 bg-teal text-white px-4 py-2.5 rounded-xl shadow-lg text-[13px] font-medium animate-in slide-in-from-top-2">
          <CheckCircle size={15} /> Profile saved
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 stagger">
        {/* ── Left column: identity card + tax summary + quick-fill */}
        <div className="space-y-4 stagger">
          {/* Identity */}
          <Card className="p-5 flex flex-col items-center text-center">
            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-primary to-navy text-white flex items-center justify-center text-[20px] font-bold mb-3">
              {initials}
            </div>
            <p className="font-semibold text-[15px] text-ink">{name}</p>
            <p className="text-[12px] text-ink-soft mb-3">{email}</p>
            <Badge tone="low"><ShieldCheck size={11} className="mr-1 inline" /> Verified</Badge>

            {/* Completeness ring */}
            <div className="w-full mt-4 pt-4 border-t border-line">
              <div className="flex items-center justify-between mb-1.5">
                <p className="text-[11.5px] font-medium text-ink-soft">Profile completeness</p>
                <p className={`text-[12px] font-bold ledger-num ${completenessColor}`}>{completeness}%</p>
              </div>
              <div className="h-1.5 rounded-full bg-line overflow-hidden">
                <div className={`h-full rounded-full transition-all ${completenessRing}`} style={{ width: `${completeness}%` }} />
              </div>
              {completeness < 60 && (
                <p className="text-[11px] text-saffron mt-2 flex items-center gap-1">
                  <AlertTriangle size={11} /> Complete profile for better advice
                </p>
              )}
            </div>

            <button
              onClick={logout}
              className="mt-4 w-full h-9 rounded-lg border border-line text-ink-soft hover:text-danger hover:border-danger/30 text-[13px] font-medium flex items-center justify-center gap-2 transition-colors"
            >
              <LogOut size={13} /> Sign out
            </button>
          </Card>

          {/* Quick-Fill Panel */}
          <Card className="p-5 border border-primary/20 bg-primary/2">
            <div className="flex items-center gap-2 mb-3">
              <Zap size={16} className="text-primary animate-pulse" />
              <p className="text-[13.5px] font-bold text-ink">Quick-Fill Demo Profiles</p>
            </div>
            <p className="text-[11.5px] text-ink-soft mb-3 leading-relaxed">
              Instantly populate the form and synchronize with the database to see live tax updates:
            </p>
            <div className="space-y-2">
              <button
                type="button"
                onClick={() => {
                  const techSalaried = {
                    dob: '1992-06-15',
                    pan: 'ABCDE1234F',
                    aadhaarLast4: '5678',
                    state: 'Karnataka',
                    residentialStatus: 'resident' as const,
                    maritalStatus: 'single' as const,
                    dependents: 0,
                    profession: 'salaried' as const,
                    employerName: 'Infosys Limited',
                    businessType: '',
                    salaryCtc: 1600000,
                    salaryInHand: 1250000,
                    businessIncome: 0,
                    freelanceIncome: 0,
                    rentalIncome: 0,
                    capitalGainsStcg: 0,
                    capitalGainsLtcg: 0,
                    otherIncome: 0,
                    dividendIncome: 0,
                    ppf: 100000,
                    elss: 50000,
                    npsEmployee: 50000,
                    npsEmployer: 0,
                    lic: 0,
                    ulip: 0,
                    fd5yr: 0,
                    sukanyaSamriddhi: 0,
                    nsc: 0,
                    homeLoanPrincipal: 0,
                    healthInsuranceSelf: 20000,
                    healthInsuranceParents: 0,
                    eduLoanInterest: 0,
                    homeLoanInterest: 0,
                    homeLoanInterest80EEA: 0,
                    evLoanInterest: 0,
                    savingsBankInterest: 8000,
                    donationsU80G: 0,
                    hra: 180000,
                    lta: 0,
                    hasProperty: false,
                    propertyType: '' as const,
                    propertyPurchaseCost: 0,
                    propertyPurchaseYear: 0,
                    propertyLoanOutstanding: 0,
                    hasVehicle: false,
                    vehicleType: '' as const,
                    vehicleUsage: '' as const,
                    vehiclePurchaseValue: 0,
                    goldValue: 0,
                    equityPortfolioValue: 120000,
                    mutualFundValue: 80000,
                    taxRegime: 'new' as const,
                    isHUF: false,
                    filingStatus: 'individual' as const,
                    seniorParents: false,
                    superSeniorParents: false
                  };
                  setDraft(techSalaried);
                  saveProfile(techSalaried);
                }}
                className="w-full h-8 text-[12px] font-medium rounded-lg bg-white border border-line hover:border-primary text-ink text-left px-3 hover:bg-primary/5 transition-colors flex items-center justify-between"
              >
                <span>💻 Tech Salaried Professional</span>
                <ChevronRight size={12} className="text-ink-soft" />
              </button>
              <button
                type="button"
                onClick={() => {
                  const freelancer = {
                    dob: '1995-11-20',
                    pan: 'PQRST5678X',
                    aadhaarLast4: '1234',
                    state: 'Maharashtra',
                    residentialStatus: 'resident' as const,
                    maritalStatus: 'single' as const,
                    dependents: 1,
                    profession: 'freelancer' as const,
                    employerName: '',
                    businessType: '',
                    salaryCtc: 0,
                    salaryInHand: 0,
                    businessIncome: 0,
                    freelanceIncome: 950000,
                    rentalIncome: 0,
                    capitalGainsStcg: 0,
                    capitalGainsLtcg: 0,
                    otherIncome: 0,
                    dividendIncome: 0,
                    ppf: 80000,
                    elss: 20000,
                    npsEmployee: 0,
                    npsEmployer: 0,
                    lic: 0,
                    ulip: 0,
                    fd5yr: 0,
                    sukanyaSamriddhi: 0,
                    nsc: 0,
                    homeLoanPrincipal: 0,
                    healthInsuranceSelf: 15000,
                    healthInsuranceParents: 0,
                    eduLoanInterest: 0,
                    homeLoanInterest: 0,
                    homeLoanInterest80EEA: 0,
                    evLoanInterest: 0,
                    savingsBankInterest: 5000,
                    donationsU80G: 0,
                    hra: 0,
                    lta: 0,
                    hasProperty: false,
                    propertyType: '' as const,
                    propertyPurchaseCost: 0,
                    propertyPurchaseYear: 0,
                    propertyLoanOutstanding: 0,
                    hasVehicle: false,
                    vehicleType: '' as const,
                    vehicleUsage: '' as const,
                    vehiclePurchaseValue: 0,
                    goldValue: 0,
                    equityPortfolioValue: 50000,
                    mutualFundValue: 30000,
                    taxRegime: 'new' as const,
                    isHUF: false,
                    filingStatus: 'individual' as const,
                    seniorParents: false,
                    superSeniorParents: false
                  };
                  setDraft(freelancer);
                  saveProfile(freelancer);
                }}
                className="w-full h-8 text-[12px] font-medium rounded-lg bg-white border border-line hover:border-primary text-ink text-left px-3 hover:bg-primary/5 transition-colors flex items-center justify-between"
              >
                <span>🎨 Freelance Designer</span>
                <ChevronRight size={12} className="text-ink-soft" />
              </button>
              <button
                type="button"
                onClick={() => {
                  const businessOwner = {
                    dob: '1988-03-04',
                    pan: 'ZZZZZ9999Z',
                    aadhaarLast4: '9876',
                    state: 'Delhi',
                    residentialStatus: 'resident' as const,
                    maritalStatus: 'married' as const,
                    dependents: 3,
                    profession: 'business_owner' as const,
                    employerName: '',
                    businessType: 'Retail Outlets',
                    salaryCtc: 0,
                    salaryInHand: 0,
                    businessIncome: 2400000,
                    freelanceIncome: 0,
                    rentalIncome: 60000,
                    capitalGainsStcg: 40000,
                    capitalGainsLtcg: 80000,
                    otherIncome: 12000,
                    dividendIncome: 8000,
                    ppf: 150000,
                    elss: 0,
                    npsEmployee: 50000,
                    npsEmployer: 0,
                    lic: 24000,
                    ulip: 0,
                    fd5yr: 0,
                    sukanyaSamriddhi: 0,
                    nsc: 0,
                    homeLoanPrincipal: 0,
                    healthInsuranceSelf: 25000,
                    healthInsuranceParents: 35000,
                    eduLoanInterest: 0,
                    homeLoanInterest: 0,
                    homeLoanInterest80EEA: 0,
                    evLoanInterest: 0,
                    savingsBankInterest: 12000,
                    donationsU80G: 0,
                    hra: 0,
                    lta: 0,
                    hasProperty: true,
                    propertyType: 'self_occupied' as const,
                    propertyPurchaseCost: 4200000,
                    propertyPurchaseYear: 2018,
                    propertyLoanOutstanding: 1400000,
                    hasVehicle: true,
                    vehicleType: 'car' as const,
                    vehicleUsage: 'commercial' as const,
                    vehiclePurchaseValue: 800000,
                    goldValue: 400000,
                    equityPortfolioValue: 650000,
                    mutualFundValue: 450000,
                    taxRegime: 'old' as const,
                    isHUF: false,
                    filingStatus: 'individual' as const,
                    seniorParents: true,
                    superSeniorParents: false
                  };
                  setDraft(businessOwner);
                  saveProfile(businessOwner);
                }}
                className="w-full h-8 text-[12px] font-medium rounded-lg bg-white border border-line hover:border-primary text-ink text-left px-3 hover:bg-primary/5 transition-colors flex items-center justify-between"
              >
                <span>🏬 Retail Store Owner</span>
                <ChevronRight size={12} className="text-ink-soft" />
              </button>
            </div>
          </Card>

          {/* Live tax summary */}
          {tax.grossIncome > 0 ? (
            <Card className="p-5 bg-gradient-to-br from-navy to-navy-deep text-white border-0 shadow-xl">
              <p className="text-[10.5px] font-semibold uppercase tracking-wide text-white/50 mb-3">
                Live Estimate · {TAX_YEAR}
              </p>
              <p className="text-[11px] text-white/50 mb-0.5">Total tax liability</p>
              <p className="ledger-num font-display font-bold text-[26px] leading-none mb-3">
                {formatINR(tax.totalTax)}
              </p>
              <div className="grid grid-cols-2 gap-3 pt-3 border-t border-white/10 text-[11px]">
                <div>
                  <p className="text-white/40">Gross income</p>
                  <p className="ledger-num font-semibold text-[13px]">{formatINR(tax.grossIncome)}</p>
                </div>
                <div>
                  <p className="text-white/40">Effective rate</p>
                  <p className="ledger-num font-semibold text-[13px]">{tax.effectiveRate.toFixed(1)}%</p>
                </div>
                <div>
                  <p className="text-white/40">Deductions</p>
                  <p className="ledger-num font-semibold text-[13px]">{formatINR(tax.totalDeductions)}</p>
                </div>
                <div>
                  <p className="text-white/40">Pot. savings</p>
                  <p className="ledger-num font-semibold text-[13px] text-saffron-light">{formatINR(tax.potentialSavings)}</p>
                </div>
              </div>
              <div className="mt-3 pt-3 border-t border-white/10">
                <span className={`text-[11px] font-medium px-2 py-0.5 rounded-md ${tax.regime === 'new' ? 'bg-teal/20 text-teal-light' : 'bg-saffron/20 text-saffron-light'}`}>
                  {tax.regime === 'new' ? 'New Regime' : 'Old Regime'}
                </span>
              </div>
            </Card>
          ) : (
            <Card className="p-5 bg-paper text-ink-soft text-center border border-line border-dashed">
              <p className="text-[12px] font-medium">No income data populated yet.</p>
              <p className="text-[11px] text-ink-soft mt-1">Fill Step 2 to view live tax estimates.</p>
            </Card>
          )}

          <div className="flex items-start gap-2 p-3 rounded-xl bg-primary/5 border border-primary/15">
            <Info size={13} className="text-primary mt-0.5 shrink-0" />
            <p className="text-[11.5px] text-ink-soft leading-relaxed">
              Your profile powers all AI suggestions. The more complete it is, the more precise your advice.
            </p>
          </div>
        </div>

        {/* ── Right column: editable sections */}
        <div className="lg:col-span-2 space-y-3 stagger">

          {/* Stepped Progress Tracker Stepper */}
          <Card className="p-4 bg-paper border border-line">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <BarChart3 size={15} className="text-primary" />
                <p className="text-[12.5px] font-bold text-ink">Completeness Progress Checklist</p>
              </div>
              <p className="text-[11.5px] text-ink-soft">Current Completeness: <strong className="text-primary">{completeness}%</strong></p>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
              {[
                { label: '1. Personal', checked: !!profile.dob && !!profile.state },
                { label: '2. Income', checked: profile.salaryCtc > 0 || profile.businessIncome > 0 || profile.freelanceIncome > 0 },
                { label: '3. Savings', checked: profile.ppf > 0 || profile.elss > 0 || profile.healthInsuranceSelf > 0 || profile.npsEmployee > 0 },
                { label: '4. Assets', checked: profile.hasProperty || profile.hasVehicle || profile.goldValue > 0 },
                { label: '5. Regime', checked: !!profile.taxRegime }
              ].map((step, idx) => (
                <div 
                  key={idx} 
                  className={`p-2 rounded-lg border text-center transition-all ${
                    step.checked 
                      ? 'border-teal/40 bg-teal/5 text-teal' 
                      : 'border-line bg-paper/50 text-ink-soft'
                  }`}
                >
                  <p className="text-[10px] font-bold truncate">{step.label}</p>
                  <p className="text-[9.5px] mt-0.5 font-medium">{step.checked ? '✅ Done' : '⏳ Pending'}</p>
                </div>
              ))}
            </div>
          </Card>

          {/* ─ Personal Info ─ */}
          <Section
            icon={User} eyebrow="Step 1" title="Personal Information"
            isOpen={openSection === 'personal'} onToggle={() => toggle('personal')}
            onSave={() => save('personal')} isEditing={openSection === 'personal'}
          >
            <div className="p-3 mb-3 bg-primary/5 rounded-xl border border-primary/10 flex gap-2">
              <Info size={14} className="text-primary mt-0.5 shrink-0" />
              <p className="text-[11.5px] text-ink-soft leading-normal">
                Make sure to provide correct identification details. Date of birth calculates age for senior citizen slab qualifications. Your residential status determines whether global or India-only incomes are taxable.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              {inp('Date of Birth (YYYY-MM-DD)', draft.dob, set('dob'), { type: 'text', placeholder: '1990-01-01' })}
              {inp('PAN (e.g. ABCDE1234F)', draft.pan, set('pan'), { placeholder: 'ABCDE1234F' })}
              {inp('Aadhaar (last 4 digits)', draft.aadhaarLast4, set('aadhaarLast4'), { placeholder: '1234' })}
              {sel('State / UT', draft.state, set('state'), INDIAN_STATES.map((s) => ({ value: s, label: s })))}
              {sel('Residential Status', draft.residentialStatus, set('residentialStatus'), [
                { value: 'resident', label: 'Resident Indian (Global taxation)' },
                { value: 'nri', label: 'Non-Resident Indian (NRI - India income only)' },
                { value: 'rnor', label: 'RNOR (Temporary resident rules)' },
              ])}
              {sel('Marital Status', draft.maritalStatus, set('maritalStatus'), [
                { value: 'single', label: 'Single' },
                { value: 'married', label: 'Married' },
                { value: 'widowed', label: 'Widowed' },
              ])}
            </div>
            <div className="grid grid-cols-2 gap-4">
              {inp('Number of dependents', draft.dependents, set('dependents'), { type: 'number', max: 10 })}
            </div>
            <div className="flex flex-col gap-3">
              {tog('Senior parents (60+) — extra 80D medical premium limit ₹50,000', draft.seniorParents, set('seniorParents'))}
              {tog('Super senior parents (80+) — medical premium limit ₹50,000', draft.superSeniorParents, set('superSeniorParents'))}
            </div>
          </Section>

          {/* ─ Profession & Income ─ */}
          <Section
            icon={Briefcase} eyebrow="Step 2" title="Profession & Income"
            isOpen={openSection === 'profession'} onToggle={() => toggle('profession')}
            onSave={() => save('profession')} isEditing={openSection === 'profession'}
          >
            <div className="p-3 mb-3 bg-primary/5 rounded-xl border border-primary/10 flex gap-2">
              <Info size={14} className="text-primary mt-0.5 shrink-0" />
              <p className="text-[11.5px] text-ink-soft leading-normal">
                Standard Deduction is automatically applied based on profession (₹75,000 for salaried employees in the New Regime; ₹50,000 in Old). Freelancers and business owners can deduct professional overhead costs directly.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              {sel('Profession', draft.profession, set('profession'), [
                { value: 'salaried', label: 'Salaried Employee' },
                { value: 'business_owner', label: 'Business Owner' },
                { value: 'freelancer', label: 'Freelancer / Consultant' },
                { value: 'professional', label: 'Professional (CA / Doctor / Lawyer)' },
                { value: 'retired', label: 'Retired' },
                { value: 'student', label: 'Student' },
              ])}
              {draft.profession === 'salaried' && inp('Employer Name', draft.employerName, set('employerName'), { placeholder: 'Company Pvt Ltd', type: 'text' })}
            </div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft">Income Sources (Annual)</p>
            <div className="grid grid-cols-2 gap-4">
              {(draft.profession === 'salaried' || draft.profession === '') && (
                <>
                  {inp('Salary CTC', draft.salaryCtc, set('salaryCtc'), { prefix: '₹', step: 50000 })}
                  {inp('Salary In-Hand', draft.salaryInHand, set('salaryInHand'), { prefix: '₹', step: 50000 })}
                  {inp('HRA Exemption Claimed (Rent paid)', draft.hra, set('hra'), { prefix: '₹' })}
                  {inp('LTA Exemption (Leave Travel)', draft.lta, set('lta'), { prefix: '₹' })}
                </>
              )}
              {(draft.profession === 'business_owner' || draft.profession === 'professional') && (
                <>
                  {inp('Business / Professional Income', draft.businessIncome, set('businessIncome'), { prefix: '₹', step: 50000 })}
                  {inp('Business Type', draft.businessType, set('businessType'), { placeholder: 'e.g. Retail, IT Services', type: 'text' })}
                </>
              )}
              {draft.profession === 'freelancer' && inp('Freelance Income', draft.freelanceIncome, set('freelanceIncome'), { prefix: '₹', step: 10000 })}
              {inp('Rental Income (from properties)', draft.rentalIncome, set('rentalIncome'), { prefix: '₹' })}
              {inp('Capital Gains STCG (15% tax)', draft.capitalGainsStcg, set('capitalGainsStcg'), { prefix: '₹' })}
              {inp('Capital Gains LTCG (10% above ₹1.25L)', draft.capitalGainsLtcg, set('capitalGainsLtcg'), { prefix: '₹' })}
              {inp('Other Income (Savings interest, etc.)', draft.otherIncome, set('otherIncome'), { prefix: '₹' })}
              {inp('Dividend Income', draft.dividendIncome, set('dividendIncome'), { prefix: '₹' })}
            </div>
          </Section>

          {/* ─ Investments & Deductions ─ */}
          <Section
            icon={PiggyBank} eyebrow="Step 3" title="Investments & Deductions"
            isOpen={openSection === 'investments'} onToggle={() => toggle('investments')}
            onSave={() => save('investments')} isEditing={openSection === 'investments'}
          >
            <div className="p-3 mb-3 bg-primary/5 rounded-xl border border-primary/10 flex gap-2">
              <Info size={14} className="text-primary mt-0.5 shrink-0" />
              <p className="text-[11.5px] text-ink-soft leading-normal">
                Deductions like 80C and 80D are primarily eligible in the <strong>Old Regime</strong>. National Pension Scheme (NPS) contribution offers an extra ₹50,000 deduction under Section 80CCD(1B) above 80C.
              </p>
            </div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft">Section 80C (limit ₹1,50,000)</p>
            <div className="grid grid-cols-2 gap-4">
              {inp('PPF (Public Provident Fund)', draft.ppf, set('ppf'), { prefix: '₹', max: 150000 })}
              {inp('ELSS / Tax-saving Mutual Fund', draft.elss, set('elss'), { prefix: '₹', max: 150000 })}
              {inp('LIC Insurance Premium', draft.lic, set('lic'), { prefix: '₹' })}
              {inp('ULIP (Unit Linked Plans)', draft.ulip, set('ulip'), { prefix: '₹' })}
              {inp('5-Year Tax-Saver Fixed Deposit', draft.fd5yr, set('fd5yr'), { prefix: '₹' })}
              {inp('NSC (National Savings Certificate)', draft.nsc, set('nsc'), { prefix: '₹' })}
              {inp('Sukanya Samriddhi (Girl Child scheme)', draft.sukanyaSamriddhi, set('sukanyaSamriddhi'), { prefix: '₹' })}
              {inp('Home Loan Principal Repaid', draft.homeLoanPrincipal, set('homeLoanPrincipal'), { prefix: '₹' })}
            </div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft">NPS (outside 80C limit)</p>
            <div className="grid grid-cols-2 gap-4">
              {inp('NPS Employee (80CCD(1B), max ₹50K)', draft.npsEmployee, set('npsEmployee'), { prefix: '₹', max: 50000 })}
              {inp('NPS Employer Contribution (80CCD(2))', draft.npsEmployer, set('npsEmployer'), { prefix: '₹' })}
            </div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft">Insurance & Loans</p>
            <div className="grid grid-cols-2 gap-4">
              {inp('Health Insurance — Self/Family (80D, max ₹25K)', draft.healthInsuranceSelf, set('healthInsuranceSelf'), { prefix: '₹', max: 25000 })}
              {inp('Health Insurance — Parents (80D, max ₹50K)', draft.healthInsuranceParents, set('healthInsuranceParents'), { prefix: '₹', max: 50000 })}
              {inp('Home Loan Interest (Sec 24b, max ₹2L)', draft.homeLoanInterest, set('homeLoanInterest'), { prefix: '₹', max: 200000 })}
              {inp('Extra Home Loan Interest (80EEA first-home ₹1.5L)', draft.homeLoanInterest80EEA, set('homeLoanInterest80EEA'), { prefix: '₹', max: 150000 })}
              {inp('EV Loan Interest (80EEB, max ₹1.5L)', draft.evLoanInterest, set('evLoanInterest'), { prefix: '₹', max: 150000 })}
              {inp('Education Loan Interest (80E, no limit)', draft.eduLoanInterest, set('eduLoanInterest'), { prefix: '₹' })}
              {inp('Savings Account Interest (80TTA, max ₹10K)', draft.savingsBankInterest, set('savingsBankInterest'), { prefix: '₹', max: 10000 })}
              {inp('Donations u/s 80G', draft.donationsU80G, set('donationsU80G'), { prefix: '₹' })}
            </div>
          </Section>

          {/* ─ Assets ─ */}
          <Section
            icon={Home} eyebrow="Step 4" title="Assets & Property"
            isOpen={openSection === 'assets'} onToggle={() => toggle('assets')}
            onSave={() => save('assets')} isEditing={openSection === 'assets'}
          >
            <div className="p-3 mb-3 bg-primary/5 rounded-xl border border-primary/10 flex gap-2">
              <Info size={14} className="text-primary mt-0.5 shrink-0" />
              <p className="text-[11.5px] text-ink-soft leading-normal">
                Declare your primary property and vehicles. Vehicles used for commercial/business operations are eligible for GST Input Tax Credit (ITC) and annual depreciation.
              </p>
            </div>
            <div className="space-y-4">
              {tog('I own a property', draft.hasProperty, set('hasProperty'))}
              {draft.hasProperty && (
                <div className="grid grid-cols-2 gap-4 pl-4 border-l-2 border-primary/20">
                  {sel('Property Type', draft.propertyType, set('propertyType'), [
                    { value: 'self_occupied', label: 'Self-Occupied' },
                    { value: 'rented', label: 'Let Out / Rented' },
                    { value: 'vacant', label: 'Vacant' },
                  ])}
                  {inp('Purchase Cost', draft.propertyPurchaseCost, set('propertyPurchaseCost'), { prefix: '₹', step: 100000 })}
                  {inp('Purchase Year', draft.propertyPurchaseYear, set('propertyPurchaseYear'), { placeholder: '2018', max: 2025 })}
                  {inp('Outstanding Loan', draft.propertyLoanOutstanding, set('propertyLoanOutstanding'), { prefix: '₹', step: 50000 })}
                </div>
              )}

              {tog('I own a vehicle', draft.hasVehicle, set('hasVehicle'))}
              {draft.hasVehicle && (
                <div className="grid grid-cols-2 gap-4 pl-4 border-l-2 border-primary/20">
                  {sel('Vehicle Type', draft.vehicleType, set('vehicleType'), [
                    { value: 'two_wheeler', label: 'Two Wheeler' },
                    { value: 'car', label: 'Car / SUV' },
                    { value: 'ev', label: 'Electric Vehicle (EV)' },
                  ])}
                  {sel('Usage', draft.vehicleUsage, set('vehicleUsage'), [
                    { value: 'personal', label: 'Personal Use' },
                    { value: 'commercial', label: 'Business / Commercial Use' },
                  ])}
                  {inp('Purchase Value', draft.vehiclePurchaseValue, set('vehiclePurchaseValue'), { prefix: '₹', step: 50000 })}
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                {inp('Gold Value (approx)', draft.goldValue, set('goldValue'), { prefix: '₹', step: 10000 })}
                {inp('Equity Portfolio Value', draft.equityPortfolioValue, set('equityPortfolioValue'), { prefix: '₹', step: 50000 })}
                {inp('Mutual Fund Value', draft.mutualFundValue, set('mutualFundValue'), { prefix: '₹', step: 10000 })}
              </div>
            </div>
          </Section>

          {/* ─ Tax Preference ─ */}
          <Section
            icon={Shield} eyebrow="Step 5" title="Tax Regime & Preferences"
            isOpen={openSection === 'tax'} onToggle={() => toggle('tax')}
            onSave={() => save('tax')} isEditing={openSection === 'tax'}
          >
            <div className="grid grid-cols-1 gap-4">
              <div>
                <p className="text-[12px] font-medium text-ink-soft mb-2">Tax Regime (FY 2025-26)</p>
                <div className="grid grid-cols-2 gap-3">
                  {(['new', 'old'] as const).map((r) => (
                    <button
                      key={r}
                      onClick={() => setDraft((d) => ({ ...d, taxRegime: r }))}
                      className={`p-4 rounded-xl border text-left transition-all ${draft.taxRegime === r ? 'border-primary bg-primary/5 ring-2 ring-primary/20' : 'border-line hover:border-primary/30'}`}
                    >
                      <p className="text-[13.5px] font-semibold text-ink mb-1">{r === 'new' ? 'New Regime' : 'Old Regime'}</p>
                      <p className="text-[11.5px] text-ink-soft">
                        {r === 'new'
                          ? '₹75K std deduction, lower slab rates, no 80C/D deductions. Rebate up to ₹7L. Best for simple filing.'
                          : '₹50K std deduction + allows all 80C, 80D, 24b deductions. Rebate up to ₹5L. Best for high investors.'}
                      </p>
                    </button>
                  ))}
                </div>
              </div>
              {tog('Part of a Hindu Undivided Family (HUF)', draft.isHUF, set('isHUF'))}
            </div>
          </Section>

        </div>
      </div>
    </AppLayout>
  );
}
