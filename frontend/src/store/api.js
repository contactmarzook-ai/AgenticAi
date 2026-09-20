import axios from 'axios';
import { useAuthStore } from './authStore';

const api = axios.create({
  baseURL: 'http://localhost:8000/api',
});

// Intercept requests to inject the JWT token
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
}, (error) => {
  return Promise.reject(error);
});

// Handle 401s globally
api.interceptors.response.use((response) => response, (error) => {
  if (error.response && error.response.status === 401) {
    useAuthStore.getState().logout();
  }
  return Promise.reject(error);
});

export default api;
