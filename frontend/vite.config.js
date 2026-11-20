import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development the API runs on :8000; in production nginx/ingress serves both under one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
