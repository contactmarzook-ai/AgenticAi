import { create } from 'zustand';
import { jwtDecode } from 'jwt-decode';

export const useAuthStore = create((set) => ({
  token: null,
  user: null, // { email, role, etc }

  setToken: (token) => {
    if (token) {
      const decoded = jwtDecode(token);
      set({ token, user: { email: decoded.sub, role: decoded.role } });
    } else {
      set({ token: null, user: null });
    }
  },

  logout: () => set({ token: null, user: null }),
}));
