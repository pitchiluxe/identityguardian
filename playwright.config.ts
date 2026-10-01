import { defineConfig } from '@playwright/test';
// One worker: browser flows share the bootstrapped synthetic organization and run in file order.
export default defineConfig({
  testDir: './tests/e2e', workers: 1, reporter: 'list',
  use: { baseURL: 'http://localhost:8000', headless: true },
  projects: [
    { name: 'setup', testMatch: /global\.setup\.ts/ },
    { name: 'e2e', testMatch: /.*\.spec\.ts/, dependencies: ['setup'] },
  ],
});
