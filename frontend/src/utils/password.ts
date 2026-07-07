export interface PasswordRule {
  key: string;
  label: string;
  test: (p: string) => boolean;
}

export const PASSWORD_RULES: PasswordRule[] = [
  { key: 'length', label: 'At least 8 characters', test: (p) => p.length >= 8 },
  { key: 'upper', label: 'One uppercase letter', test: (p) => /[A-Z]/.test(p) },
  { key: 'lower', label: 'One lowercase letter', test: (p) => /[a-z]/.test(p) },
  { key: 'number', label: 'One number', test: (p) => /[0-9]/.test(p) },
  { key: 'special', label: 'One special character', test: (p) => /[^A-Za-z0-9]/.test(p) },
];

const COMMON_PASSWORDS = new Set([
  'password', 'password1', '12345678', 'qwerty123', 'letmein', 'admin123',
  'welcome1', 'iloveyou', '123456789', 'abc12345',
]);

export interface PasswordStrengthResult {
  checks: Record<string, boolean>;
  score: number;
  label: string;
  isCommon: boolean;
  meetsMinimum: boolean;
}

export function checkPasswordStrength(password = ''): PasswordStrengthResult {
  const checks = PASSWORD_RULES.reduce((acc, rule) => {
    acc[rule.key] = rule.test(password);
    return acc;
  }, {} as Record<string, boolean>);

  const passedCount = Object.values(checks).filter(Boolean).length;
  const isCommon = COMMON_PASSWORDS.has(password.toLowerCase());

  let score = 0;
  if (password.length > 0) score = Math.max(1, passedCount - 1);
  if (password.length >= 12 && passedCount >= 4) score = 4;
  if (isCommon) score = Math.min(score, 1);

  const LABELS = ['Very weak', 'Weak', 'Fair', 'Good', 'Strong'];
  const label = password.length === 0 ? '' : LABELS[Math.min(score, 4)];

  const meetsMinimum = !!(checks.length && checks.upper && checks.lower && checks.number && !isCommon);

  return { checks, score: Math.min(score, 4), label, isCommon, meetsMinimum };
}
