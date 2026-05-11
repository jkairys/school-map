import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  base: '/admin/',
  server: {
    proxy: {
      // All API calls proxy to FastAPI in dev.
      // No /api prefix — the SPA calls paths like /scrape-lists, /jobs, etc.
      // directly so fetch() paths work identically in dev and prod.
      '/scrape-lists': 'http://localhost:8000',
      '/scrape-runs': 'http://localhost:8000',
      '/suburbs': 'http://localhost:8000',
      '/jobs': 'http://localhost:8000',
      '/properties': 'http://localhost:8000',
      '/listings': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
