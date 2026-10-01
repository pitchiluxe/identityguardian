import { test, expect } from '@playwright/test';
import { open, signIn } from './helpers';

test('mock Entra connector syncs as a worker job in its own sandbox environment', async ({ page }) => {
  test.setTimeout(120_000);
  await signIn(page, 'alex');
  const name = `Connector sandbox ${Date.now()}`;
  await open(page, 'Administration');
  await page.getByRole('textbox', { name: 'Environment name' }).fill(name);
  await page.getByRole('button', { name: 'Create sandbox' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Sandbox environment' })).toBeVisible();
  await page.getByRole('button', { name: 'Refresh' }).click();
  await page.getByRole('combobox', { name: 'Environment' }).selectOption({ label: name });
  await open(page, 'Integrations');
  await expect(page.getByText(/never contact a real tenant/)).toBeVisible();
  await page.getByRole('button', { name: 'Register mock connector' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Connector registered' })).toBeVisible();
  await page.getByRole('row').filter({ hasText: 'Mock Entra' }).getByRole('button', { name: 'Queue full sync' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Full sync queued' })).toBeVisible();
  await expect(async () => {
    await page.getByRole('button', { name: 'Refresh' }).click();
    await expect(page.getByRole('row').filter({ hasText: 'Mock Entra' }).getByText('HEALTHY')).toBeVisible({ timeout: 3000 });
  }).toPass({ timeout: 60_000 });
});
