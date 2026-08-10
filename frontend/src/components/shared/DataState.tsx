import { AlertTriangle, Inbox, Loader2, RefreshCw } from 'lucide-react';
import type { ReactNode } from 'react';

/**
 * The three states every data view must handle, now that mockData fallbacks
 * are gone (DEM-002).
 *
 * The error state is deliberately prominent. In a tax product a missing number
 * is safe and a wrong number is not, so "we could not load this" has to be
 * unmissable rather than a quiet grey line.
 */

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12 text-ink-soft">
      <Loader2 size={20} className="animate-spin text-primary" />
      <p className="text-[13px]">{label}</p>
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  what = 'this information',
}: {
  error: Error;
  onRetry?: () => void;
  what?: string;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-3 rounded-xl border border-saffron/40 bg-saffron/5 px-6 py-10 text-center"
    >
      <AlertTriangle size={20} className="text-saffron" />
      <div>
        <p className="text-[13.5px] font-semibold text-ink">
          Could not load {what}
        </p>
        <p className="mt-1 text-[12.5px] text-ink-soft">{error.message}</p>
        <p className="mt-2 text-[11.5px] text-ink-soft">
          No figures are shown here rather than estimated ones.
        </p>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-1 inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-[12.5px] font-medium text-ink hover:border-primary/40"
        >
          <RefreshCw size={12} />
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center gap-2 py-12 text-center text-ink-soft">
      <Inbox size={20} />
      <p className="text-[13.5px] font-medium text-ink">{title}</p>
      {hint && <p className="text-[12.5px] max-w-sm">{hint}</p>}
    </div>
  );
}

/**
 * Render helper so a page can express all three states in one expression
 * instead of three nested ternaries.
 */
export function DataView<T>({
  state,
  what,
  children,
  empty,
}: {
  state: { data: T | null; loading: boolean; error: Error | null; refetch: () => void };
  what?: string;
  children: (data: T) => ReactNode;
  empty?: ReactNode;
}) {
  if (state.loading) return <LoadingState />;
  if (state.error) {
    return <ErrorState error={state.error} onRetry={state.refetch} what={what} />;
  }
  if (state.data === null || state.data === undefined) {
    return <>{empty ?? <EmptyState title="Nothing to show yet" />}</>;
  }
  return <>{children(state.data)}</>;
}
