import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The browser talks only to the Vite origin; /api is forwarded to FastAPI. Because of that
// the backend needs no CORS middleware in development.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: process.env.VITE_API_TARGET ?? 'http://localhost:8000', changeOrigin: true },
    },
  },
})
