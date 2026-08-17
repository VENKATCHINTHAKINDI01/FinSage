import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Without this, a component left mounted by one test is found by the next
// test's query and the suite passes on the wrong element.
afterEach(cleanup);
