import { test, expect } from '@playwright/test';
import { open, signIn } from './helpers';

test('machine identities show ownerless and expiring credential evidence and propose rotation', async ({ page }) => {
  await signIn(page, 'casey');
  await open(page, 'Machine identities');
  await expect(page.getByText(/Secret values are stripped at ingestion/)).toBeVisible();
  const card = page.locator('details.finding').filter({ hasText: 'svc-erp-sync' });
  await card.locator('summary').click();
  await expect(card.getByText('No owner')).toBeVisible();
  await expect(card.getByText('Credential expiring')).toBeVisible();
  await card.getByRole('row').filter({ hasText: 'cert-erp-sync' }).getByRole('button', { name: 'Propose rotation' }).click();
  await expect(page.getByRole('heading', { name: /Rotate credential/ })).toBeVisible();
  await page.getByRole('button', { name: 'Simulate' }).click();
  await expect(page.getByRole('heading', { name: 'Bound simulation' })).toBeVisible();
});
