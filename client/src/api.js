// src/api.js
// Tiny fetch client — attaches the JWT (from localStorage) to every request.

const TOKEN_KEY = 'jobpilot_token';

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, { method = 'GET', body, isForm = false } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (!isForm && body !== undefined) headers['Content-Type'] = 'application/json';

  const res = await fetch(`/api${path}`, {
    method,
    headers,
    body: isForm ? body : body !== undefined ? JSON.stringify(body) : undefined,
  });

  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }

  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    if (typeof data?.detail === 'string') message = data.detail;
    else if (Array.isArray(data?.detail)) message = data.detail.map((d) => d.msg).join('; ');
    throw new ApiError(message, res.status);
  }
  return data;
}

export const api = {
  register: (email, password) => request('/auth/register', { method: 'POST', body: { email, password } }),
  login: (email, password) => request('/auth/login', { method: 'POST', body: { email, password } }),
  me: () => request('/auth/me'),

  getProfile: () => request('/profile'),
  updateProfile: (body) => request('/profile', { method: 'PUT', body }),
  uploadResume: (file) => {
    const form = new FormData();
    form.append('file', file);
    return request('/profile/resume', { method: 'POST', body: form, isForm: true });
  },
  removeResume: () => request('/profile/resume', { method: 'DELETE' }),

  getFeed: () => request('/companies/feed'),
  startScrape: () => request('/companies/scrape', { method: 'POST' }),
  scrapeStatus: () => request('/companies/scrape/status'),
  draftEmail: (companyId) => request(`/companies/${companyId}/draft`, { method: 'POST' }),
  sendEmail: (companyId, body) => request(`/companies/${companyId}/send`, { method: 'POST', body }),
  skipCompany: (companyId) => request(`/companies/${companyId}/skip`, { method: 'POST' }),

  getSentEmails: () => request('/tracker/sent-emails'),
  checkReplies: () => request('/tracker/check-replies', { method: 'POST' }),
  sendFollowups: () => request('/tracker/send-followups', { method: 'POST' }),

  getNotifications: () => request('/replies/notifications'),
  markNotifRead: (id) => request(`/replies/notifications/${id}/read`, { method: 'POST' }),
  getDrafts: () => request('/replies/drafts'),
  approveDraft: (id, body) => request(`/replies/drafts/${id}/approve`, { method: 'POST', body }),
  rejectDraft: (id) => request(`/replies/drafts/${id}/reject`, { method: 'POST' }),

  getSchedulerStatus: () => request('/scheduler/status'),
  startScheduler: () => request('/scheduler/start', { method: 'POST' }),
  stopScheduler: () => request('/scheduler/stop', { method: 'POST' }),
};

export { ApiError };
