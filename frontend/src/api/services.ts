import api from './client';

// ── Auth ──────────────────────────────────────────────────────────────────────

export async function login(email: string, password: string) {
  const res = await api.post('/api/v1/auth/login', { email, password });
  return {
    access_token: res.access_token,
    // Was dropped here — the access token expires in 15 minutes and
    // nothing else can renew it without this.
    refresh_token: res.refresh_token,
    name: email.split('@')[0],
    email,
  };
}

export async function register(params: { name: string; email: string; password: string }) {
  // Returns AuthTokenResponse (access_token + refresh_token)
  const res = await api.post('/api/v1/auth/register', {
    full_name: params.name,
    email: params.email,
    password: params.password,
  });
  return {
    access_token: res.access_token,
    refresh_token: res.refresh_token,
    name: params.name,
    email: params.email,
  };
}

export async function logoutSession(refreshToken: string) {
  return api.post('/api/v1/auth/logout', { refresh_token: refreshToken });
}

export async function getMe() {
  return api.get('/api/v1/auth/me');
}

// ── Health Score ──────────────────────────────────────────────────────────────

export async function getHealthScore(params: { include_breakdown?: boolean } = {}) {
  return api.post('/api/v1/reports/health-score', { include_breakdown: true, ...params });
}

// ── Compliance ────────────────────────────────────────────────────────────────

export async function getComplianceReport(params: Record<string, unknown> = {}) {
  return api.post('/api/v1/compliance/report', params);
}

export async function getAuditHistory() {
  return api.get('/api/v1/compliance/audit-history');
}

export async function getITRStatus() {
  return api.get('/api/v1/compliance/itr-status');
}

// ── ITR Guide ─────────────────────────────────────────────────────────────────

export async function getITRGuidance(params: Record<string, unknown> = {}) {
  return api.post('/api/v1/compliance/filing', params);
}

// ── Tax Calculator ────────────────────────────────────────────────────────────

export async function calculateAdvancedTax(params: Record<string, unknown> = {}) {
  return api.post('/api/v1/compliance/calculator', params);
}

// ── Reports ───────────────────────────────────────────────────────────────────

export async function getReportsList() {
  return api.get('/api/v1/reports/list');
}

export async function generateReport(type: string) {
  return api.post('/api/v1/reports/generate', { report_type: type });
}

// ── Notifications ─────────────────────────────────────────────────────────────

export async function getNotificationPreferences() {
  return api.get('/api/v1/notifications/preferences');
}

export async function setNotificationPreferences(params: {
  channel: string;
  enabled: boolean;
  frequency?: string;
  preferred_time?: string;
}) {
  return api.post('/api/v1/notifications/preferences', params);
}

export async function getNotificationHistory() {
  return api.get('/api/v1/notifications/history');
}

// ── Chat ──────────────────────────────────────────────────────────────────────

export async function sendChatQuery(query: string, conversation_id?: string) {
  return api.post('/api/v1/chat/query', { query, conversation_id });
}

// ── Benefits ──────────────────────────────────────────────────────────────────

export async function getBenefits(params: Record<string, unknown> = {}) {
  return api.post('/api/v1/benefits/discover', params);
}

export async function checkEligibility(params: Record<string, unknown> = {}) {
  return api.post('/api/v1/benefits/eligibility', params);
}

// ── Profile Sync ──────────────────────────────────────────────────────────────

export async function getProfile() {
  return api.get('/api/v1/profile');
}

export async function updateProfile(profileData: any) {
  return api.post('/api/v1/profile', profileData);
}
