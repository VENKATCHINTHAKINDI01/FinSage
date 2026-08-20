import { useState, useRef, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Send, Sparkles, CheckCircle, AlertTriangle, XCircle, RefreshCw, ShoppingBag } from 'lucide-react';
import { useProfileStore, buildAIContext, calculateTax, marginalRateAt, profileCompleteness, TAX_YEAR } from '../../store/useProfileStore';
import type { FinancialProfile } from '../../store/useProfileStore';
import { sendChatQuery } from '../../api/services';
import { formatINR } from '../../utils/format';

// ── Types ────────────────────────────────────────────────────────────────────

type Role = 'user' | 'ai' | 'system';
type Verdict = 'green' | 'yellow' | 'red' | null;

interface Message {
  id: string;
  role: Role;
  text: string;
  quickReplies?: string[];
  isTyping?: boolean;
  verdict?: Verdict;
  verdictData?: VerdictData;
}

interface VerdictData {
  verdict: Verdict;
  headline: string;
  summary: string;
  taxSavings: number;
  affordability: string;
  topTip: string;
}

// ── Purchase categories ───────────────────────────────────────────────────────

const CATEGORIES = [
  { id: 'vehicle', label: '🚗 Vehicle', keywords: ['car', 'bike', 'scooter', 'vehicle', 'ev', 'electric', 'auto', 'truck', 'suv'] },
  { id: 'property', label: '🏠 Property', keywords: ['house', 'flat', 'apartment', 'property', 'land', 'home', 'plot', 'office'] },
  { id: 'electronics', label: '💻 Electronics', keywords: ['laptop', 'phone', 'mobile', 'iphone', 'tablet', 'computer', 'camera', 'macbook'] },
  { id: 'gold', label: '📿 Gold/Jewellery', keywords: ['gold', 'jewellery', 'jewelry', 'silver', 'diamond', 'ornament'] },
  { id: 'appliance', label: '🏠 Appliance', keywords: ['fridge', 'ac', 'washing machine', 'television', 'tv', 'refrigerator', 'microwave'] },
  { id: 'investment', label: '📈 Investment', keywords: ['stock', 'mutual fund', 'nps', 'fd', 'bond', 'elss', 'ppf', 'insurance'] },
  { id: 'general', label: '🛒 General', keywords: [] },
];

function detectCategory(text: string) {
  const lower = text.toLowerCase();
  for (const cat of CATEGORIES) {
    if (cat.keywords.some((k) => lower.includes(k))) return cat;
  }
  return CATEGORIES.find((c) => c.id === 'general')!;
}

// ── Question flows per category ───────────────────────────────────────────────

const FLOWS: Record<string, { question: string; replies?: string[] }[]> = {
  vehicle: [
    { question: 'Is this for personal use or business/commercial use?', replies: ['Personal use', 'Business/commercial use', 'Both'] },
    { question: 'What\'s your approximate budget for this vehicle?', replies: ['Under ₹5L', '₹5L–₹15L', '₹15L–₹30L', 'Above ₹30L'] },
    { question: 'Are you considering an Electric Vehicle (EV) or a petrol/diesel vehicle?', replies: ['Electric Vehicle (EV)', 'Petrol', 'Diesel', 'Hybrid'] },
    { question: 'Will you take a loan or pay cash/full amount?', replies: ['Taking a loan', 'Paying cash', 'Partly cash + partly loan'] },
  ],
  property: [
    { question: 'Is this for self-occupation or as an investment / rental property?', replies: ['Self-occupation (home)', 'Investment/rental', 'Both (live for now, rent later)'] },
    { question: 'Is this your first property purchase?', replies: ['Yes, first property', 'No, I already own property'] },
    { question: 'What\'s your approximate budget?', replies: ['Under ₹30L', '₹30L–₹75L', '₹75L–₹1.5Cr', 'Above ₹1.5Cr'] },
    { question: 'Are you taking a home loan?', replies: ['Yes, home loan', 'No, paying cash', 'Partly loan'] },
  ],
  electronics: [
    { question: 'Will this be used for work/business or personal use?', replies: ['Primarily work/business', 'Purely personal', 'Both work and personal'] },
    { question: 'What\'s your approximate budget?', replies: ['Under ₹20K', '₹20K–₹60K', '₹60K–₹1.5L', 'Above ₹1.5L'] },
    { question: 'Are you a business owner / freelancer / salaried employee who can get employer reimbursement?', replies: ['Yes, business owner/freelancer', 'Salaried — can request reimbursement', 'No, fully personal purchase'] },
  ],
  gold: [
    { question: 'Are you looking at physical gold or digital gold (Sovereign Gold Bonds / ETFs)?', replies: ['Physical gold/jewellery', 'Sovereign Gold Bonds (SGBs)', 'Gold ETFs / Funds', 'Not sure yet'] },
    { question: 'What\'s the purpose of this purchase?', replies: ['Investment', 'Gifting / family occasion', 'Jewellery for personal use', 'Emergency reserve'] },
    { question: 'What\'s your approximate budget?', replies: ['Under ₹50K', '₹50K–₹2L', '₹2L–₹5L', 'Above ₹5L'] },
  ],
  appliance: [
    { question: 'Is this for your home or for a business/rental property?', replies: ['Personal home use', 'Rental property (business)', 'Office/business'] },
    { question: 'What\'s your budget range?', replies: ['Under ₹20K', '₹20K–₹50K', '₹50K–₹1L', 'Above ₹1L'] },
  ],
  investment: [
    { question: 'What are you planning to invest in?', replies: ['ELSS / Mutual Funds', 'NPS', 'Fixed Deposit', 'PPF', 'Stocks / ETFs', 'Insurance'] },
    { question: 'What\'s your investment goal?', replies: ['Tax saving', 'Retirement', 'Short-term growth', 'Wealth preservation'] },
    { question: 'How much are you planning to invest?', replies: ['Under ₹50K', '₹50K–₹1.5L', '₹1.5L–₹5L', 'Above ₹5L'] },
  ],
  general: [
    { question: 'Could you tell me a bit more about what you\'re planning to buy?', replies: [] },
    { question: 'What\'s your approximate budget for this purchase?', replies: ['Under ₹10K', '₹10K–₹50K', '₹50K–₹2L', 'Above ₹2L'] },
    { question: 'Is this for personal use or business/work purposes?', replies: ['Personal', 'Business/work'] },
  ],
};

// ── AI verdict builder (offline, instant) ─────────────────────────────────────

function buildOfflineVerdict(
  category: string,
  answers: string[],
  profile: FinancialProfile,
  _itemDesc: string
): VerdictData {
  const tax = calculateTax(profile);
  const income = tax.grossIncome;
  const budgetStr = answers.find((a) => a.includes('₹') || a.includes('L')) || '';
  const isBusinessUse = answers.some((a) => a.toLowerCase().includes('business') || a.toLowerCase().includes('commercial') || a.toLowerCase().includes('work'));
  const isEV = answers.some((a) => a.toLowerCase().includes('ev') || a.toLowerCase().includes('electric'));
  const isFirstProperty = answers.some((a) => a.toLowerCase().includes('first property'));
  const isLoan = answers.some((a) => a.toLowerCase().includes('loan'));

  // Rough budget extraction
  let budgetMax = 500000;
  if (budgetStr.includes('30L') || budgetStr.includes('75L')) budgetMax = 7500000;
  else if (budgetStr.includes('15L') || budgetStr.includes('1.5Cr')) budgetMax = 15000000;
  else if (budgetStr.includes('5L') || budgetStr.includes('50K')) budgetMax = 500000;
  else if (budgetStr.includes('Above ₹30L') || budgetStr.includes('Above ₹1.5Cr')) budgetMax = 20000000;

  // Affordability: EMI rule — should be < 40% of monthly income
  const monthlyIncome = income / 12;
  const emi = isLoan ? (budgetMax * 0.009) : 0; // ~0.9% per month rough EMI
  const affordabilityRatio = monthlyIncome > 0 ? emi / monthlyIncome : 0;

  let verdict: Verdict = 'green';
  if (affordabilityRatio > 0.5) verdict = 'red';
  else if (affordabilityRatio > 0.3 || budgetMax > income * 1.5) verdict = 'yellow';

  // Tax savings calc — valued at the real marginal rate for this profile's
  // regime and taxable income, not a flat 30% regardless of actual bracket.
  const marginalRate = marginalRateAt(tax.taxableIncome, profile.taxRegime);
  let taxSavings = 0;
  if (isEV) taxSavings += 150000 * marginalRate;
  if (category === 'property' && isFirstProperty && isLoan) taxSavings += 350000 * marginalRate;
  if (isBusinessUse && category === 'vehicle') taxSavings += budgetMax * 0.15 * marginalRate;
  if (isBusinessUse && category === 'electronics') taxSavings += budgetMax * marginalRate;

  const verdictMap = {
    green: {
      headline: '✅ Looks like a good buy!',
      summary: `Based on your income of ${formatINR(income)} and this purchase at ~${formatINR(budgetMax)}, this appears financially sound${taxSavings > 0 ? ` with ₹${Math.round(taxSavings).toLocaleString('en-IN')} in potential tax savings` : ''}.`,
    },
    yellow: {
      headline: '⚠️ Proceed with caution',
      summary: `This purchase is somewhat stretching your budget. Your EMI would be ~${formatINR(Math.round(emi))}/month — about ${Math.round(affordabilityRatio * 100)}% of your monthly income. Consider a smaller down payment or wait for a salary increment.`,
    },
    red: {
      headline: '🔴 Recommended: Wait or reduce budget',
      summary: `At ~${formatINR(budgetMax)}, this purchase may create financial stress. The estimated EMI (${formatINR(Math.round(emi))}/month) is too high relative to your income. We recommend building more savings first or reducing the budget.`,
    },
  };

  const topTips: Record<string, string> = {
    vehicle: isEV
      ? 'Claim ₹1,50,000 EV loan interest deduction under Section 80EEB — saves up to ₹45,000 in tax.'
      : isBusinessUse
      ? 'Register as commercial vehicle and claim 15% depreciation + GST ITC as a business expense.'
      : 'Buy before March 31 to claim depreciation this financial year if under business use.',
    property: isFirstProperty && isLoan
      ? 'As a first-time buyer, claim ₹2L (Sec 24b) + ₹1.5L (80EEA) = ₹3.5L interest deduction annually.'
      : 'Claim ₹2L home loan interest under Section 24b in the old regime.',
    electronics: isBusinessUse
      ? 'Claim 100% of cost as business expense under Section 37 — get full tax deduction immediately.'
      : 'If salaried, request employer to reimburse via tax-free tech allowance policy.',
    gold: 'Sovereign Gold Bonds (SGBs) give 2.5% annual interest + LTCG exemption on maturity. Much better than physical gold.',
    investment: 'Invest in ELSS before March 31 for 80C deduction. Lock-in is only 3 years vs 15 years for PPF.',
    general: 'If business-related, keep invoice and claim as business expense. Personal purchases have no direct tax benefit.',
  };

  return {
    verdict,
    headline: verdictMap[verdict].headline,
    summary: verdictMap[verdict].summary,
    taxSavings: Math.round(taxSavings),
    affordability: income > 0 ? `${Math.round(affordabilityRatio * 100)}% of monthly income` : 'Complete your income profile for EMI affordability',
    topTip: topTips[category] || topTips.general,
  };
}

// ── Main Component ────────────────────────────────────────────────────────────

const uid = () => Math.random().toString(36).slice(2);

export default function PurchaseAdvisorChat() {
  const { profile } = useProfileStore();
  const [messages, setMessages] = useState<Message[]>([
    {
      id: uid(),
      role: 'ai',
      text: 'Hi! I\'m your Smart Purchase Advisor 👋\n\nTell me what you\'re thinking of buying — a car, laptop, property, gold, or anything else — and I\'ll help you figure out the smartest way to buy it, including tax-saving strategies and whether it fits your current financial situation.',
      quickReplies: ['I want to buy a car', 'Looking to buy a laptop', 'Planning to buy a house', 'Thinking of buying gold', 'Something else'],
    },
  ]);

  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [conversationId] = useState(uid());
  const [step, setStep] = useState(0);
  const [category, setCategory] = useState<(typeof CATEGORIES)[0] | null>(null);
  const [itemDesc, setItemDesc] = useState('');
  const [answers, setAnswers] = useState<string[]>([]);
  const [phase, setPhase] = useState<'detect' | 'questions' | 'analyzing' | 'done'>('detect');
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const addMessage = useCallback((msg: Omit<Message, 'id'>) => {
    setMessages((prev) => [...prev, { id: uid(), ...msg }]);
  }, []);

  const showTyping = useCallback((duration: number) => {
    return new Promise<void>((resolve) => {
      setIsTyping(true);
      setTimeout(() => { setIsTyping(false); resolve(); }, duration);
    });
  }, []);

  const handleUserMessage = useCallback(async (text: string) => {
    if (!text.trim()) return;
    addMessage({ role: 'user', text });
    setInput('');

    // Phase: detect category from first message
    if (phase === 'detect') {
      const cat = detectCategory(text);
      setCategory(cat);
      setItemDesc(text);

      await showTyping(1000);
      const flow = FLOWS[cat.id] || FLOWS.general;
      addMessage({
        role: 'ai',
        text: `Great! I'll help you analyze this ${cat.label} purchase. Let me ask a few quick questions to give you the most accurate advice.\n\n${flow[0].question}`,
        quickReplies: flow[0].replies,
      });
      setPhase('questions');
      setStep(0);
      return;
    }

    // Phase: ask questions from flow
    if (phase === 'questions' && category) {
      const newAnswers = [...answers, text];
      setAnswers(newAnswers);
      const flow = FLOWS[category.id] || FLOWS.general;
      const nextStep = step + 1;

      if (nextStep < flow.length) {
        await showTyping(700);
        addMessage({
          role: 'ai',
          text: flow[nextStep].question,
          quickReplies: flow[nextStep].replies,
        });
        setStep(nextStep);
        return;
      }

      // All questions answered — analyze
      setPhase('analyzing');
      await showTyping(500);
      addMessage({
        role: 'ai',
        text: `Perfect! I have everything I need. Let me analyze this purchase against your financial profile and search for the best strategies…`,
      });

      // Call backend AI with profile context
      await showTyping(2000);
      const profileContext = buildAIContext(profile);
      const fullQuery = `
I want to buy: ${itemDesc}
Category: ${category.label}
My answers to advisor questions:
${newAnswers.map((a, i) => `${i + 1}. ${a}`).join('\n')}

${profileContext}

Please analyze this purchase for me:
1. Is this a financially sound decision given my profile?
2. What are all the tax-saving strategies I can use for this purchase (Section 80EEB, 32, 37, 54, etc.)?
3. What is the most efficient way to buy this (loan vs cash, timing, online vs offline, negotiation tips)?
4. What is the impact on my financial health (EMI affordability, debt ratio)?
5. Give me a final recommendation.

Keep your response concise, structured, and specific to my numbers.
`.trim();

      let aiResponse = '';
      try {
        const res = await sendChatQuery(fullQuery, conversationId);
        aiResponse = res?.response || res?.message || res?.content || JSON.stringify(res);
      } catch {
        aiResponse = `Based on your profile and this ${category.label.split(' ').slice(1).join(' ')} purchase, here's my analysis:\n\n**Key consideration:** Your gross income is ${profile.salaryCtc > 0 ? formatINR(profile.salaryCtc) : 'not yet set in your profile'}. Make sure to complete your profile for personalized affordability calculations.\n\nFor the best buying strategy and tax optimization, check the Smart Savings strategies panel on the left.`;
      }

      // Build offline verdict card (instant, doesn't need AI)
      const verdictData = buildOfflineVerdict(category.id, newAnswers, profile, itemDesc);

      addMessage({ role: 'ai', text: aiResponse });

      await showTyping(800);
      addMessage({
        role: 'ai',
        text: '',
        verdict: verdictData.verdict,
        verdictData,
      });
      setPhase('done');
      return;
    }

    // Phase: done — general follow-up chat
    if (phase === 'done') {
      await showTyping(1000);
      try {
        const res = await sendChatQuery(text, conversationId);
        addMessage({ role: 'ai', text: res?.response || res?.message || 'Let me know if you have more questions about this purchase!' });
      } catch {
        addMessage({ role: 'ai', text: 'I\'m here to help! Ask me anything else about optimizing this purchase.' });
      }
    }
  }, [phase, category, step, answers, itemDesc, profile, addMessage, showTyping, conversationId]);

  function handleReset() {
    setMessages([{
      id: uid(),
      role: 'ai',
      text: 'Sure! Tell me about another purchase you\'re considering.',
      quickReplies: ['I want to buy a car', 'Looking to buy a laptop', 'Planning to buy a house', 'Something else'],
    }]);
    setPhase('detect');
    setStep(0);
    setCategory(null);
    setItemDesc('');
    setAnswers([]);
    setInput('');
  }

  return (
    <div className="flex flex-col h-[680px] rounded-2xl border border-line overflow-hidden bg-white shadow-lg">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3.5 bg-gradient-to-r from-navy to-navy-deep border-b border-white/10 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-saffron to-teal flex items-center justify-center">
            <Sparkles size={16} className="text-white" />
          </div>
          <div>
            <p className="text-[13.5px] font-bold text-white">Smart Purchase Advisor</p>
            <p className="text-[10.5px] text-white/45">AI-powered · Profile-aware · {TAX_YEAR}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {phase === 'done' && (
            <button
              onClick={handleReset}
              className="flex items-center gap-1.5 text-[11.5px] font-medium text-white/60 hover:text-white px-2.5 py-1 rounded-lg hover:bg-white/10 transition-all"
            >
              <RefreshCw size={12} /> New query
            </button>
          )}
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-teal/20 border border-teal/30">
            <span className="w-1.5 h-1.5 rounded-full bg-teal animate-pulse" />
            <span className="text-[10.5px] font-semibold text-teal-light">Live</span>
          </div>
        </div>
      </div>
      {profileCompleteness(profile) < 50 && (
        <div className="bg-saffron/10 border-b border-saffron/20 px-5 py-2.5 flex items-center justify-between gap-3 shrink-0">
          <div className="flex items-center gap-2">
            <AlertTriangle size={14} className="text-saffron shrink-0" />
            <p className="text-[11.5px] text-ink font-medium">
              Profile incomplete. Finish setting up your profile for exact tax savings & EMI checks.
            </p>
          </div>
          <Link 
            to="/profile" 
            className="text-[11px] font-bold text-primary hover:underline shrink-0 bg-white px-2.5 py-1 rounded-lg border border-line"
          >
            Complete Profile
          </Link>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-5 space-y-4 bg-slate-50/50">
        {messages.map((msg) => (
          <div key={msg.id}>
            {/* Verdict card */}
            {msg.verdict && msg.verdictData && (
              <div className={`rounded-2xl p-4 mb-3 animate-scale-in ${
                msg.verdict === 'green' ? 'verdict-green' :
                msg.verdict === 'yellow' ? 'verdict-yellow' : 'verdict-red'
              }`}>
                <div className="flex items-center gap-2 mb-2">
                  {msg.verdict === 'green' && <CheckCircle size={18} className="text-teal" />}
                  {msg.verdict === 'yellow' && <AlertTriangle size={18} className="text-saffron" />}
                  {msg.verdict === 'red' && <XCircle size={18} className="text-danger" />}
                  <p className="font-bold text-[14px] text-ink">{msg.verdictData.headline}</p>
                </div>
                <p className="text-[12.5px] text-ink-soft leading-relaxed mb-3">{msg.verdictData.summary}</p>
                <div className="grid grid-cols-2 gap-2 mb-3">
                  <div className="p-2.5 rounded-xl bg-white/70 border border-white/80">
                    <p className="text-[10px] text-ink-soft font-medium mb-0.5">Potential tax saving</p>
                    <p className="ledger-num font-bold text-[14px] text-teal">{msg.verdictData.taxSavings > 0 ? formatINR(msg.verdictData.taxSavings) : '—'}</p>
                  </div>
                  <div className="p-2.5 rounded-xl bg-white/70 border border-white/80">
                    <p className="text-[10px] text-ink-soft font-medium mb-0.5">EMI affordability</p>
                    <p className="font-bold text-[12px] text-ink">{msg.verdictData.affordability}</p>
                  </div>
                </div>
                <div className="flex items-start gap-2 p-2.5 rounded-xl bg-white/60 border border-white/80">
                  <Sparkles size={12} className="text-primary mt-0.5 shrink-0" />
                  <p className="text-[12px] text-ink font-medium">{msg.verdictData.topTip}</p>
                </div>
              </div>
            )}

            {/* Text messages */}
            {msg.text && (
              <div className={`flex items-end gap-2.5 ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
                {msg.role === 'ai' && (
                  <div className="w-7 h-7 rounded-full bg-gradient-to-br from-primary to-teal flex items-center justify-center shrink-0 mb-0.5">
                    <Sparkles size={13} className="text-white" />
                  </div>
                )}
                <div
                  className={`max-w-[82%] rounded-2xl px-4 py-3 text-[13px] leading-relaxed whitespace-pre-wrap ${
                    msg.role === 'user'
                      ? 'chat-bubble-right bg-primary text-white rounded-br-md'
                      : 'chat-bubble-left bg-white border border-line text-ink shadow-sm rounded-bl-md'
                  }`}
                >
                  {msg.text}
                </div>
                {msg.role === 'user' && (
                  <div className="w-7 h-7 rounded-full bg-gradient-to-br from-saffron to-primary flex items-center justify-center shrink-0 mb-0.5 text-white text-[11px] font-bold">
                    U
                  </div>
                )}
              </div>
            )}

            {/* Quick replies */}
            {msg.quickReplies && msg.quickReplies.length > 0 && phase !== 'done' && (
              <div className={`flex flex-wrap gap-2 mt-2.5 ${msg.role === 'ai' ? 'ml-9' : 'justify-end'}`}>
                {msg.quickReplies.map((reply) => (
                  <button
                    key={reply}
                    onClick={() => handleUserMessage(reply)}
                    className="quick-reply"
                  >
                    {reply}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}

        {/* Typing indicator */}
        {isTyping && (
          <div className="flex items-end gap-2.5">
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-primary to-teal flex items-center justify-center shrink-0">
              <Sparkles size={13} className="text-white" />
            </div>
            <div className="bg-white border border-line rounded-2xl rounded-bl-md px-4 py-3.5 shadow-sm">
              <div className="flex items-center gap-1.5">
                <div className="w-2 h-2 rounded-full bg-ink-soft typing-dot-1" />
                <div className="w-2 h-2 rounded-full bg-ink-soft typing-dot-2" />
                <div className="w-2 h-2 rounded-full bg-ink-soft typing-dot-3" />
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="shrink-0 p-4 border-t border-line bg-white">
        {phase === 'done' && (
          <p className="text-[11px] text-ink-soft text-center mb-2.5">
            Analysis complete · Ask follow-up questions or{' '}
            <button onClick={handleReset} className="text-primary font-semibold underline">start a new query</button>
          </p>
        )}
        <div className="flex items-center gap-3">
          <div className="flex-1 relative">
            <ShoppingBag size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-soft" />
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleUserMessage(input); } }}
              placeholder={phase === 'detect' ? 'Tell me what you want to buy…' : phase === 'done' ? 'Ask a follow-up question…' : 'Type your answer or pick above…'}
              className="w-full h-11 pl-9 pr-4 rounded-xl border border-line bg-paper text-[13.5px] text-ink placeholder:text-ink-soft focus:outline-none focus:ring-2 focus:ring-primary/25 focus:border-primary transition-all"
            />
          </div>
          <button
            onClick={() => handleUserMessage(input)}
            disabled={!input.trim() || isTyping}
            className="w-11 h-11 rounded-xl bg-primary text-white flex items-center justify-center hover:bg-primary-600 disabled:opacity-40 disabled:cursor-not-allowed transition-all hover:shadow-lg hover:shadow-primary/25 active:scale-95"
          >
            <Send size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
