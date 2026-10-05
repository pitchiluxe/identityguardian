import { test, expect } from '@playwright/test';
import { open, signIn } from './helpers';

test('integrations offers a read-only Microsoft Entra ID connection', async ({ page }) => {
  await signIn(page, 'alex');
  await open(page, 'Integrations');
  await expect(page.getByRole('heading', { name: 'Identity sources' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Connect Microsoft Entra ID (read-only)' })).toBeVisible();
  for (const name of ['Tenant ID', 'Client ID', 'Client secret']) await expect(page.getByLabel(name, { exact: true })).toBeVisible();
  await expect(page.getByLabel('Client secret', { exact: true })).toHaveAttribute('type', 'password');
  await expect(page.getByText(/read-only/i).first()).toBeVisible();
});
