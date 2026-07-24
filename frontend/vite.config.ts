import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const apiTarget = env.VITE_API_PROXY_TARGET || 'http://localhost:8080';

  return {
    plugins: [react()],
    build: {
      target: 'es2020',
      // Keep the React runtime in its own long-cached chunk; page chunks
      // (React.lazy in App.tsx) then only change when their page changes.
      rollupOptions: {
        output: {
          manualChunks(id: string) {
            if (id.includes('node_modules')) return 'vendor';
          },
        },
      },
    },
    server: {
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
        '/health': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
  };
});
