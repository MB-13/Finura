// Dev-only UI preview harness. Not part of the production build, lint or the app tsconfig.
import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  root: import.meta.dirname,
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, '../src') } },
  server: { port: 5174, strictPort: true, fs: { allow: [path.resolve(import.meta.dirname, '..')] } },
})
