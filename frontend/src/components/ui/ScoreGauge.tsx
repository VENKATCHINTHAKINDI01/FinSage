interface ScoreGaugeProps {
  // Optional and nullable: callers commonly pass a value straight from an
  // API response that has not resolved yet (undefined while loading, or a
  // field the response genuinely omits). `score / 100` on either produces
  // NaN, which React forwards straight into the `strokeDashoffset` SVG
  // attribute — an invisible bug that only shows up as a console warning,
  // not a caught error, so it is worth being deliberate about here rather
  // than trusting every call site to guard it.
  score: number | null | undefined;
  size?: number;
}

export default function ScoreGauge({ score, size = 144 }: ScoreGaugeProps) {
  const strokeWidth = 10;
  // Radius based on container size
  const radius = size / 2 - strokeWidth - 5;
  const center = size / 2;
  const circumference = 2 * Math.PI * radius;
  const safeScore = typeof score === 'number' && !Number.isNaN(score) ? score : 0;
  const strokeDashoffset = circumference - (safeScore / 100) * circumference;

  // Determine color based on score
  const getColor = (val: number) => {
    if (val >= 80) return '#10B981'; // Emerald / green
    if (val >= 60) return '#F59E0B'; // Amber / orange
    return '#EF4444'; // Red / danger
  };

  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <svg className="w-full h-full transform -rotate-90" viewBox={`0 0 ${size} ${size}`}>
        {/* Background Circle */}
        <circle
          cx={center}
          cy={center}
          r={radius}
          className="stroke-slate-100 dark:stroke-slate-800"
          strokeWidth={strokeWidth}
          fill="transparent"
        />
        {/* Progress Circle */}
        <circle
          cx={center}
          cy={center}
          r={radius}
          stroke={getColor(safeScore)}
          strokeWidth={strokeWidth}
          fill="transparent"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          className="transition-all duration-500 ease-out"
        />
      </svg>
      {/* Centered text */}
      <div className="absolute flex flex-col items-center justify-center">
        <span className="text-3xl font-black text-slate-900 dark:text-white font-display leading-none">
          {safeScore}
        </span>
        <span className="text-[10px] uppercase tracking-wider font-bold text-slate-400 dark:text-slate-500 mt-1">
          / 100
        </span>
      </div>
    </div>
  );
}
