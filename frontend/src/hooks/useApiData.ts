import { useCallback, useEffect, useState } from 'react';

/**
 * Fetch state for a single API call.
 *
 * DEM-002 — what was removed and why
 * -----------------------------------
 * This hook used to take a `mockFallback` and, on ANY error, quietly return it
 * with `isDemo: true`. Seven pages passed fabricated financial figures into
 * that slot. When the backend failed, the user saw numbers — plausible,
 * specific, entirely invented — with nothing on screen to say so.
 *
 * There is no fallback now. A failure returns `error`, and the caller must
 * render an error state. For a product where the numbers are the point,
 * showing nothing is strictly better than showing something made up.
 */

export interface ApiState<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
  /** Re-run the request, e.g. from a "Try again" button in the error state. */
  refetch: () => void;
}

export function useApiData<T>(
  apiCall: () => Promise<T>,
  dependencies: unknown[] = []
): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [attempt, setAttempt] = useState(0);

  const refetch = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    apiCall()
      .then((res) => {
        if (!active) return;
        setData(res);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (!active) return;
        // Fail loudly. Never substitute a value.
        setData(null);
        setError(err instanceof Error ? err : new Error(String(err)));
        setLoading(false);
      });

    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...dependencies, attempt]);

  return { data, loading, error, refetch };
}

export default useApiData;
