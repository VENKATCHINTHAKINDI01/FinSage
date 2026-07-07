import { useState, useEffect } from 'react';

export function useApiData<T>(
  apiCall: () => Promise<T>,
  mockFallback: any,
  dependencies: any[] = []
) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<any>(null);
  const [isDemo, setIsDemo] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    
    apiCall()
      .then((res) => {
        if (active) {
          setData(res);
          setIsDemo(false);
          setError(null);
          setLoading(false);
        }
      })
      .catch((err) => {
        console.warn("API request failed, falling back to mock data:", err);
        if (active) {
          setData(mockFallback);
          setIsDemo(true);
          setError(err);
          setLoading(false);
        }
      });
      
    return () => {
      active = false;
    };
  }, dependencies);

  return { data, loading, error, isDemo };
}
export default useApiData;
