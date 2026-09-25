import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    // Every test injects its own `fetch`; the guard makes forgetting that a failure
    // rather than a live POST to queue.fal.run (see src/test-setup.ts).
    setupFiles: ['src/test-setup.ts'],
  },
});
