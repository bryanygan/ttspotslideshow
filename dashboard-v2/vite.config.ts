import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Dev server runs on 5174 so it never collides with the existing dashboard/
// (5173) or the Python backend (8000). The backend has CORS enabled, so the
// UI talks to it cross-origin via the configurable API base.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5174,
    strictPort: false,
  },
})
