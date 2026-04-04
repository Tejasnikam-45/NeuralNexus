import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    watch: {
      // Ignore the cyberguard landing site subfolder — it has its own
      // Vite instance and its tsconfig.json changes were causing NeuralNexus
      // to do unnecessary full-reloads.
      ignored: ['**/cyberguard-ai-main/**'],
    },
  },
})
