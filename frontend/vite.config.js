import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
  },
  build: {
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: {
          react_vendor: ['react', 'react-dom'],
          ui_vendor: ['framer-motion', 'lucide-react'],
          syntax_vendor: ['react-syntax-highlighter']
        }
      }
    }
  }
})
