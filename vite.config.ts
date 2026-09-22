import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// The dev proxy target is configurable so a browser session can be pointed at a
// backend whose writable state lives in a temp directory (PATCHWORK_STATE_DIR).
// Answering exercises in a browser otherwise mutates the real learner's
// progression, hearts and mistake queue, which makes end-to-end verification of
// graded content needless risky. Unset means the normal local API.
const apiTarget = process.env.VITE_API_PROXY || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: 5173,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
    // Eight places stub the `fetch` global and only some of them undo it, so a
    // file that runs after a leaky one inherits its fake backend — which is how
    // `ProjectWorkspace.test.tsx` started answering `/session` with another
    // test's teaching ladder. Vitest resets globals after every test instead, so
    // each file sees exactly the stub it installed itself.
    unstubGlobals: true,
  },
})
