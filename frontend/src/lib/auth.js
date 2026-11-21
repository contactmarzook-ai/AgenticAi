import { create } from 'zustand';

const KEY = 'agentos.token';

// localStorage so a sign-in carries over to new tabs. The access token is short-lived
// (JWT_EXPIRE_MINUTES) and renewed from the HttpOnly session cookie (see api.js refreshSession);
// the server can revoke it at any time (sign-out, password or role change).
function readToken() {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

function writeToken(token) {
  try {
    if (token) localStorage.setItem(KEY, token);
    else localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: keep the token in memory only */
  }
}

export const useAuth = create((set) => ({
  token: readToken(),
  user: null, // from GET /auth/me: { id, email, role, department, permissions }
  expired: false,
  setToken: (token) => {
    writeToken(token);
    set({ token, expired: false });
  },
  setUser: (user) => set({ user }),
  logout: (opts = {}) => {
    writeToken(null);
    try {
      // Unsaved builder drafts belong to the person who signed out.
      Object.keys(localStorage).filter((k) => k.startsWith('agentos.unsaved.')).forEach((k) => localStorage.removeItem(k));
    } catch {
      /* ignore */
    }
    set({ token: null, user: null, expired: !!opts.expired });
  },
}));

// Signing out in one tab signs out the others.
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key === KEY && !e.newValue) useAuth.getState().logout();
  });
}

export function can(user, permission) {
  return !!user?.permissions?.includes(permission);
}
