import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: '/workspace/',
  build: {outDir: '../ros/portal/workspace', emptyOutDir: true, sourcemap: false, assetsInlineLimit: 0},
  server: {proxy: {'/api': 'http://127.0.0.1:8737', '/media': 'http://127.0.0.1:8737', '/vault': 'http://127.0.0.1:8737'}},
});
