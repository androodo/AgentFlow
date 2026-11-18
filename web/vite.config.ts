import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3001,
    strictPort: true,
    proxy: { '/api': process.env.AGENTFLOW_API_URL ?? 'http://127.0.0.1:8001' },
  },
})
