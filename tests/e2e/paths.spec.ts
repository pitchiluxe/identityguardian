import { test, expect } from '@playwright/test';
import { open, signIn } from './helpers';

test('attack paths show conditional reset exposure with defensive framing', async ({ page }) => {
  await signIn(page, 'alex');
  await open(page, 'Attack paths');
  await expect(page.getByText(/Defensive analysis only/)).toBeVisible();
  await page.getByRole('combobox', { name: 'Starting identity' }).selectOption({ label: 'Erick Mensah' });
  const path = page.locator('details.finding').filter({ hasText: 'Erick Mensah → Customer Data Store' }).first();
  await path.locator('summary').click();
  await expect(path.getByText('CONDITIONAL').first()).toBeVisible();
  await expect(path.getByText('target_mfa_registered')).toBeVisible();
  await expect(path.getByText(/Require MFA re-verification/)).toBeVisible();
});
