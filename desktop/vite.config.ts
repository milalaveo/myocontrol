import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

export default defineConfig({
  base: './',
  plugins: [react()],
  resolve: {
    alias: { '~@ibm/plex': fileURLToPath(new URL('./node_modules/@ibm/plex', import.meta.url)) },
  },
  server: { host: '127.0.0.1', port: 5174, strictPort: true },
})
