import axios from 'axios';
import { useAuth } from './auth';

// Same-origin API: the dev server proxies /api, and in production the ingress routes /api to the backend.
const api = axios.create({ baseURL: '/api', timeout: 600000 });

api.interceptors.request.use((config) => {
  const token = useAuth.getState().token;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && !error.config.url.endsWith('/auth/login')) {
      useAuth.getState().logout();
    }
    return Promise.reject(error);
  },
);

/** Turn an axios error into a readable message. */
export function errorMessage(err, fallback = 'Something went wrong') {
  const detail = err?.response?.data?.detail;
  if (!detail) return err?.message || fallback;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d) => `${(d.loc || []).slice(1).join('.')}: ${d.msg}`).join('; ');
  if (detail.errors) return `${detail.message}: ${detail.errors.join('; ')}`;
  return detail.message || JSON.stringify(detail);
}

export default api;
