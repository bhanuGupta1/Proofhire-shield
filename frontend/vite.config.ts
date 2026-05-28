import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/scan-cv': 'http://localhost:8000',
      '/trust-report': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
