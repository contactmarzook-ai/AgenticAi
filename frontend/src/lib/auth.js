import { create } from 'zustand';

const KEY = 'agentos.token';

function readToken() {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

function writeToken(token) {
  try {
    if (token) sessionStorage.setItem(KEY, token);
    else sessionStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: keep the token in memory only */
  }
}

export const useAuth = create((set) => ({
  token: readToken(),
  user: null, // from GET /auth/me: { id, email, role, department, permissions }
  setToken: (token) => {
    writeToken(token);
    set({ token });
  },
  setUser: (user) => set({ user }),
  logout: () => {
    writeToken(null);
    set({ token: null, user: null });
  },
}));

export function can(user, permission) {
  return !!user?.permissions?.includes(permission);
}
