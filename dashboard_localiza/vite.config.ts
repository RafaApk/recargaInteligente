import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Configuração mínima: o projeto original usava plugins do Figma Make, que não são necessários aqui.
export default defineConfig({
  base: './',
  plugins: [react()],
  server: { port: 5173 },
})
