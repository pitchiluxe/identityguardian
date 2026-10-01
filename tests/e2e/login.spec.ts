import { test, expect } from '@playwright/test';
import { signIn } from './helpers';

test('real OIDC login shows scoped workspace and logout revokes session', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('link', { name: 'Sign in with your identity provider' })).toBeVisible();
  await signIn(page, 'alex');
  await expect(page.getByText('Contoso Global Technologies')).toBeAttached();
  await page.screenshot({ path: 'docs/screenshots/phase-1-workspace.png', fullPage: true });
  await page.getByRole('button', { name: 'Administration', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Organization members' })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'Sam Contoso', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Labs Planned', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Labs is planned' })).toBeVisible();
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Sign in with your identity provider' })).toBeVisible();
  expect((await page.request.get('/api/v1/session')).status()).toBe(401);
});

test('viewer cannot open administrative data through UI or direct API', async ({ page }) => {
  await signIn(page, 'sam');
  await page.getByRole('button', { name: 'Administration', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Restricted to authorized roles' })).toBeVisible();
  expect((await page.request.get('/api/v1/organizations/10000000-0000-4000-8000-000000000001/members')).status()).toBe(403);
});
