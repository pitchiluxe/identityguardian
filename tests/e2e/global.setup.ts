import { test as setup, expect } from '@playwright/test';
import { signIn } from './helpers';

// Ensures the bootstrapped organization's LAB environment holds the standard SYNTHETIC fixture.
setup('seed and sync synthetic Contoso sandbox', async ({ page }) => {
  await signIn(page, 'alex');
  const session = await (await page.request.get('/api/v1/session')).json();
  const org = session.organizations[0].id;
  const envs = await (await page.request.get(`/api/v1/organizations/${org}/environments`)).json();
  const base = `/api/v1/organizations/${org}/environments/${envs.data[0].id}`;
  const headers = { 'X-CSRF-Token': session.csrf_token, Origin: 'http://localhost:8000' };
  expect((await page.request.post(base + '/sandbox/seed', { headers, data: { confirm_synthetic: true, variant: 'standard' } })).status()).toBe(200);
  expect((await page.request.post(base + '/connectors/sandbox/sync', { headers, data: { mode: 'full' } })).status()).toBe(200);
});
