const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001';

function getStoredToken(): string | null {
  try {
    const raw = localStorage.getItem('finsage_auth');
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed?.state?.token || null;
  } catch {
    return null;
  }
}

async function request(path: string, options: RequestInit = {}): Promise<any> {
  const token = getStoredToken();
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { 
      const body = await res.json(); 
      detail = body.detail || detail; 
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  get: (path: string) => request(path, { method: 'GET' }),
  post: (path: string, data?: any) => request(path, { method: 'POST', body: data ? JSON.stringify(data) : undefined }),
};

export default api;
