import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // In development the API runs separately (uvicorn on :8000); proxy /api to it so the
    // browser sees a single origin, exactly like production behind Apache.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
