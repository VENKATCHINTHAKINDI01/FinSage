import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  BarChart, Bar, PieChart, Pie, Cell, RadarChart, PolarGrid, PolarAngleAxis, Radar,
} from 'recharts';
import { formatCompactINR } from '../../utils/format';

const TOOLTIP_STYLE = {
  contentStyle: {
    background: '#0b1f33',
    border: 'none',
    borderRadius: 10,
    fontSize: 12.5,
    fontFamily: 'JetBrains Mono, monospace',
    padding: '10px 12px',
  },
  labelStyle: { color: '#94a3b8', fontFamily: 'Inter, sans-serif', marginBottom: 4 },
  itemStyle: { color: '#fff' },
};

interface HealthTrendPoint {
  month: string;
  score: number;
}

interface HealthTrendChartProps {
  data: HealthTrendPoint[];
}

export function HealthTrendChart({ data }: HealthTrendChartProps) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <defs>
          <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#1a5490" stopOpacity={0.28} />
            <stop offset="100%" stopColor="#1a5490" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke="#e3e8ef" />
        <XAxis dataKey="month" tick={{ fontSize: 11.5, fill: '#42566b' }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 11.5, fill: '#42566b' }} axisLine={false} tickLine={false} width={30} />
        <Tooltip {...TOOLTIP_STYLE} />
        <Area type="monotone" dataKey="score" stroke="#1a5490" strokeWidth={2.5} fill="url(#trendFill)" />
      </AreaChart>
    </ResponsiveContainer>
  );
}

interface IncomeVsTaxPoint {
  fy: string;
  income: number;
  tax: number;
}

interface IncomeVsTaxChartProps {
  data: IncomeVsTaxPoint[];
}

export function IncomeVsTaxChart({ data }: IncomeVsTaxChartProps) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -8, bottom: 0 }} barGap={6}>
        <CartesianGrid vertical={false} stroke="#e3e8ef" />
        <XAxis dataKey="fy" tick={{ fontSize: 11.5, fill: '#42566b' }} axisLine={false} tickLine={false} />
        <YAxis tickFormatter={(v) => formatCompactINR(Number(v))} tick={{ fontSize: 11, fill: '#42566b' }} axisLine={false} tickLine={false} width={56} />
        <Tooltip {...TOOLTIP_STYLE} formatter={(v) => formatCompactINR(Number(v))} />
        <Bar dataKey="income" fill="#1a5490" radius={[6, 6, 0, 0]} name="Gross Income" />
        <Bar dataKey="tax" fill="#d97706" radius={[6, 6, 0, 0]} name="Tax Paid" />
      </BarChart>
    </ResponsiveContainer>
  );
}

const PIE_COLORS = ['#1a5490', '#d97706', '#0d9488', '#7aa9cf', '#f5a94e'];

interface DeductionPiePoint {
  name: string;
  value: number;
}

interface DeductionPieProps {
  data: DeductionPiePoint[];
}

export function DeductionPie({ data }: DeductionPieProps) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={3}>
          {data.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
        </Pie>
        <Tooltip {...TOOLTIP_STYLE} formatter={(v) => formatCompactINR(Number(v))} />
      </PieChart>
    </ResponsiveContainer>
  );
}

interface FactorRadarPoint {
  factor: string;
  score: number;
}

interface FactorRadarProps {
  data: FactorRadarPoint[];
}

export function FactorRadar({ data }: FactorRadarProps) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <RadarChart data={data} outerRadius="75%">
        <PolarGrid stroke="#e3e8ef" />
        <PolarAngleAxis dataKey="factor" tick={{ fontSize: 11, fill: '#42566b' }} />
        <Radar dataKey="score" stroke="#1a5490" fill="#1a5490" fillOpacity={0.25} strokeWidth={2} />
        <Tooltip {...TOOLTIP_STYLE} />
      </RadarChart>
    </ResponsiveContainer>
  );
}
