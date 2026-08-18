export function formatCompactINR(value: number | null | undefined): string {
  // Matches formatINR/formatPercent below: absent data renders as an
  // explicit "—", never as NaN (which `undefined / 100000` silently
  // produces) and never as a fabricated 0.
  if (value === undefined || value === null || Number.isNaN(value)) return '—';
  if (value >= 10000000) {
    const val = (value / 10000000).toFixed(1).replace(/\.0$/, '');
    return `₹${val}Cr`;
  }
  if (value >= 100000) {
    const val = (value / 100000).toFixed(1).replace(/\.0$/, '');
    return `₹${val}L`;
  }
  if (value >= 1000) {
    const val = (value / 1000).toFixed(1).replace(/\.0$/, '');
    return `₹${val}k`;
  }
  return `₹${value}`;
}

export function formatINR(value: number | null | undefined): string {
  if (value === undefined || value === null || Number.isNaN(value)) return '—';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0
  }).format(value);
}

export function formatPercent(value: number | null | undefined): string {
  if (value === undefined || value === null || Number.isNaN(value)) return '—';
  return `${value.toFixed(1)}%`;
}

export function formatDate(dateString: string): string {
  if (!dateString) return '';
  const date = new Date(dateString);
  return new Intl.DateTimeFormat('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric'
  }).format(date);
}
