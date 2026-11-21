import axios from 'axios';
import { useAuth } from './auth';

// Same-origin API: the dev server proxies /api, and in production the ingress routes /api to the backend.
const api = axios.create({ baseURL: '/api', timeout: 600000 });

api.interceptors.request.use((config) => {
  const token = useAuth.getState().token;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Access tokens are short-lived. The server keeps the session in an HttpOnly cookie (scripts
// cannot read it); /auth/refresh swaps it for a new access token. One refresh at a time.
let refreshing = null;
export function refreshSession() {
  if (!refreshing) {
    refreshing = axios
      .post('/api/auth/refresh', null, { timeout: 15000 })
      .then((r) => {
        if (r.status === 204) throw new Error('no session');
        useAuth.getState().setToken(r.data.access_token);
        return r.data.access_token;
      })
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

/** Sign out on the server (ends the session everywhere it is used), then locally. */
export async function signOut() {
  try {
    await api.post('/auth/logout');
  } catch {
    /* already signed out or offline: still clear locally */
  }
  useAuth.getState().logout();
}

const NO_REFRESH = ['/auth/login', '/auth/refresh', '/auth/logout'];

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const cfg = error.config || {};
    const url = cfg.url || '';
    if (error.response?.status === 401 && !url.startsWith('/public/') && !NO_REFRESH.some((u) => url.endsWith(u))) {
      if (!cfg._retried && useAuth.getState().token) {
        try {
          const token = await refreshSession();
          return api({ ...cfg, _retried: true, headers: { ...cfg.headers, Authorization: `Bearer ${token}` } });
        } catch {
          /* fall through: the session is over */
        }
      }
      useAuth.getState().logout({ expired: true });
    }
    return Promise.reject(error);
  },
);

/** Turn an axios error into a readable message. */
function friendlyField(loc) {
  const name = String((loc || []).slice(-1)[0] ?? 'value').replace(/_/g, ' ');
  return name.charAt(0).toUpperCase() + name.slice(1);
}

function friendlyValidation(d) {
  const field = friendlyField(d.loc);
  if (d.type === 'string_too_short' || d.type === 'missing') return `${field} is required`;
  if (d.type === 'string_too_long') return `${field} is too long (max ${d.ctx?.max_length} characters)`;
  if (d.type === 'value_error' && d.msg) return `${field}: ${d.msg.replace(/^Value error, /, '')}`;
  return `${field}: ${d.msg}`;
}

export function errorMessage(err, fallback = 'Something went wrong') {
  if (!err?.response) return 'Cannot reach the server. Check your connection and try again.';
  if (err.response.status === 429) return err.response.data?.detail || 'Too many requests. Please wait a moment.';
  if (err.response.status >= 500) return 'The server had a problem. Please try again; if it keeps happening, tell your administrator.';
  const detail = err?.response?.data?.detail;
  if (!detail) return err?.message || fallback;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(friendlyValidation).join('; ');
  if (detail.errors) return `${detail.message}: ${detail.errors.join('; ')}`;
  return detail.message || JSON.stringify(detail);
}

export default api;
