import { defineConfig } from 'vite';
import path from 'node:path';
import fs from 'node:fs';

export default defineConfig({
  root: 'static',
  base: '/',
  build: {
    outDir: '../dist',
    emptyOutDir: false, // build-nodes.js and static assets populate dist
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, 'static/index.html')
      }
    }
  },
  server: {
    port: 3000,
    proxy: {
      '/nodes': 'http://127.0.0.1:8000',
      '/flows': 'http://127.0.0.1:8000',
      '/settings': 'http://127.0.0.1:8000',
      '/locales': 'http://127.0.0.1:8000',
      '/icons': 'http://127.0.0.1:8000',
      '/comms': {
        target: 'ws://127.0.0.1:8000',
        ws: true
      }
    }
  }
});

