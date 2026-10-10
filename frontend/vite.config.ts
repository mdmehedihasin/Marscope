import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
  base: './', // relative asset paths: works from any folder, e.g. GitHub Pages /<repo>/
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000', '/layers': 'http://127.0.0.1:8000' } },
});
