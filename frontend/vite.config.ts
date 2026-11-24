import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '~@ibm/plex': fileURLToPath(new URL('./node_modules/@ibm/plex', import.meta.url)) },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  build: { rollupOptions: { output: { manualChunks: { react: ['react', 'react-dom'] } } } },
})
