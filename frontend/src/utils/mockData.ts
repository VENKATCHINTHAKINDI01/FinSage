// Fallback demo data — mirrors the shapes returned by the FastAPI backend
// (Steps 4-10). Pages use this when the API is unreachable so the product
// is always explorable.

export const mockHealthScore = {
  overall_score: 78,
  health_status: { level: 'Good', emoji: '🟡', message: 'Good health with room for improvement', color: '#d97706' },
  trend: { status: '↑ 4 points', previous_score: 74, change: 4, direction: '↑' },
  breakdown: {
    tax_efficiency: { score: 82, weight: '20%', description: 'How efficiently you manage tax liability' },
    deduction_optimization: { score: 65, weight: '20%', description: 'How well you utilize available deductions' },
    savings_potential: { score: 88, weight: '20%', description: 'Potential for additional tax savings' },
    compliance_status: { score: 85, weight: '20%', description: 'Your tax compliance readiness' },
    investment_diversity: { score: 70, weight: '20%', description: 'Diversification of investments for tax benefits' },
  },
  recommendations: [
    '🟡 Consider advanced tax planning techniques',
    '🔴 Maximize available deductions before year-end',
    '📊 Diversify investments for better tax optimization',
  ],
};

export const mockTaxSummary = {
  financial_year: '2025-26',
  gross_income: 1850000,
  income_breakdown: { salary: 1650000, business: 0, rental: 120000, capital_gains_stcg: 40000, capital_gains_ltcg: 40000, other_income: 0 },
  deductions: { total_claimed: 243000 },   // 75K std + 150K 80C + 18K 80D
  taxable_income: 1607000,
  tax_calculation: { income_tax: 254050, surcharge: 0, cess: 10162, total_tax_liability: 264212 },
  effective_tax_rate: 14.3,
  refund_or_balance: { estimated_refund: 0, balance_due: 39000, status: 'PAY ₹39,000' },
  optimization_suggestions: [
    { strategy: 'Maximize 80C (ELSS, PPF, NSC) — ₹32K headroom left', headroom: 32000, potential_savings: 9600, difficulty: 'Easy', action: 'Invest additional ₹32,000 in ELSS before March 31, 2026' },
    { strategy: 'Health insurance (80D) — unused ₹25K deduction', potential_savings: 7500, difficulty: 'Easy', action: 'Buy health insurance policy — ₹25,000 limit for self + family' },
    { strategy: 'NPS extra deduction (80CCD(1B)) — outside 80C limit', potential_savings: 15000, difficulty: 'Medium', action: 'Open NPS Tier-I and invest ₹50,000 — completely separate from 80C' },
    { strategy: 'Ask employer for NPS contribution (80CCD(2))', potential_savings: 49500, difficulty: 'Medium', action: 'Up to 10% of basic salary as employer NPS — ₹0 impact on your 80C limit' },
  ],
};

export const mockCompliance = {
  compliance_score: 85,
  audit_ready: true,
  audit_readiness_status: '✅ Audit Ready',
  risk_level: '🟢 LOW RISK - Audit unlikely',
  red_flags: [
    { flag: '⚠️ High income (₹20L+) with low deductions', severity: 'Medium' as const, action: 'Maximize valid deductions under 80C, 80D, 80E before March 31, 2026' },
  ],
  missing_documents: ['Investment Receipts (80C)', 'Medical Bills (80DDB)'],
  recommendations: ['🟢 Ready to file ITR for AY 2026-27', 'Gather missing documents: Investment Receipts (80C)'],
  itr_deadline: 'July 31, 2026',
  days_to_deadline: 25,
};

export const mockITR = {
  recommended_form: 'ITR-2',
  form_details: { name: 'Individuals with capital gains or foreign assets', applicable: 'Capital gains, foreign assets, speculation income', complexity: '🟡 Moderate' },
  financial_year: '2025-26',
  step_by_step_guide: [
    { step: 1, action: 'Visit incometax.gov.in', details: "Go to e-filing portal, click 'File ITR'", time_min: 2 },
    { step: 2, action: 'Login with PAN + Password', details: 'Use your registered email & password', time_min: 2 },
    { step: 3, action: 'Select Assessment Year 2026-27', details: 'Select AY 2026-27 for FY 2025-26', time_min: 1 },
    { step: 4, action: 'Select ITR Form', details: 'Select ITR-2 for salary + capital gains', time_min: 2 },
    { step: 5, action: 'Fill personal info', details: 'Name, address, contact, PAN, Aadhaar', time_min: 5 },
    { step: 6, action: 'Fill income details', details: 'Salary (from Form 16), rental, capital gains', time_min: 10 },
    { step: 7, action: 'Claim deductions', details: '80C investments, 80D health insurance, Section 24b home loan interest', time_min: 8 },
    { step: 8, action: 'Pay self-assessment tax', details: 'Pay any remaining tax via Challan 280 before filing', time_min: 5 },
    { step: 9, action: 'Verify ITR-V', details: 'e-Verify within 30 days using Aadhaar OTP or net banking', time_min: 3 },
  ],
  common_mistakes: [
    'Selecting wrong ITR form (use ITR-2 for capital gains)',
    'Not reporting all income sources including freelance, interest',
    'Missing advance tax instalments — attracts 234B/234C interest',
    'Claiming deductions without supporting documents',
    'Not verifying ITR-V within 30 days (makes filing invalid)',
    'Not reporting foreign assets under Schedule FA (for NRIs)',
  ],
  days_to_deadline: 25,
};

export const mockNotificationPrefs = {
  preferences: {
    email: { enabled: true, frequency: 'weekly', preferred_time: '09:00' },
    telegram: { enabled: false, frequency: 'as_needed', preferred_time: null },
  },
};

export const mockReports = [
  { id: '1', type: 'compliance', title: 'Compliance Assessment Report', generated: '2026-06-24T09:00:00', size: 84213, downloads: 2 },
  { id: '2', type: 'financial_health', title: 'Financial Health Report', generated: '2026-06-01T09:00:00', size: 61022, downloads: 1 },
  { id: '3', type: 'tax_summary', title: 'Tax Summary Report', generated: '2026-05-20T09:00:00', size: 73310, downloads: 4 },
];

export const mockDeductionBreakdown = [
  { name: '80C', value: 150000, limit: 150000 },
  { name: '80D', value: 25000, limit: 150000 },
  { name: '80CCD (NPS)', value: 0, limit: 150000 },
  { name: '80E', value: 43000, limit: null },
  { name: '80TTA', value: 0, limit: 10000 },
];

export const mockMonthlyTrend = [
  { month: 'Jan', score: 62 }, { month: 'Feb', score: 65 }, { month: 'Mar', score: 70 },
  { month: 'Apr', score: 68 }, { month: 'May', score: 74 }, { month: 'Jun', score: 78 },
];

export const mockIncomeVsTax = [
  { fy: 'FY 22-23', income: 1420000, tax: 187000 },
  { fy: 'FY 23-24', income: 1580000, tax: 214000 },
  { fy: 'FY 24-25', income: 1710000, tax: 251000 },
  { fy: 'FY 25-26', income: 1850000, tax: 264212 },
];
