import { Check, X } from 'lucide-react';
import clsx from 'clsx';
import { PASSWORD_RULES, checkPasswordStrength } from '../../utils/password';

const BAR_COLORS = ['#b91c1c', '#d97706', '#f5a94e', '#0d9488', '#0d9488'];
const BAR_LABELS_COLOR = ['text-danger', 'text-saffron', 'text-saffron', 'text-teal', 'text-teal'];

interface PasswordStrengthMeterProps {
  password: string;
}

export default function PasswordStrengthMeter({ password }: PasswordStrengthMeterProps) {
  const { checks, score, label, isCommon } = checkPasswordStrength(password);

  if (!password) return null;

  return (
    <div className="mt-2.5 animate-rise">
      <div className="flex gap-1.5 mb-2">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-1.5 flex-1 rounded-full bg-line overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{
                width: score > i ? '100%' : '0%',
                background: BAR_COLORS[Math.min(score, 4)],
              }}
            />
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between mb-2.5">
        <span className={clsx('text-[12px] font-medium', BAR_LABELS_COLOR[Math.min(score, 4)])}>
          {label}
        </span>
        {isCommon && (
          <span className="text-[11px] text-danger font-medium">This password is too common</span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
        {PASSWORD_RULES.map((rule) => {
          const passed = checks[rule.key];
          return (
            <div key={rule.key} className="flex items-center gap-1.5">
              <div
                className={clsx(
                  'w-3.5 h-3.5 rounded-full flex items-center justify-center shrink-0 transition-colors',
                  passed ? 'bg-teal text-white' : 'bg-line text-ink-soft'
                )}
              >
                {passed ? <Check size={9} strokeWidth={3} /> : <X size={9} strokeWidth={3} />}
              </div>
              <span className={clsx('text-[11.5px]', passed ? 'text-ink-soft' : 'text-ink-soft/70')}>
                {rule.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
