/**
 * Vitest — the runner three Phase 5 features were blocked on.
 *
 * EVD-005 and PLN-007 were both held at `tested` rather than `verified` for
 * exactly one reason: their React components had no way to run. The backend
 * halves were mutation-tested; the components were reasoned about. That is not
 * the same thing, and the registry said so rather than pretending otherwise.
 *
 * jsdom rather than a browser runner because these are unit tests of component
 * logic — what renders when provenance is missing, which tab is shown, whether
 * an assumption is addressable. Nothing here needs a real layout engine.
 */
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    coverage: { provider: 'v8', include: ['src/components/shared/**'] },
  },
});
