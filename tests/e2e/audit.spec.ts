import { test, expect } from '@playwright/test';
import { open, signIn } from './helpers';

test('auditor verifies the audit chain and creates a signed checkpoint', async ({ page }) => {
  await signIn(page, 'morgan');
  await open(page, 'Audit logs');
  await page.getByRole('button', { name: 'Create signed checkpoint' }).click();
  await expect(page.getByText(/VERIFIED · chain INTACT/)).toBeVisible();
  await expect(page.getByText(/"signature":/)).toBeVisible();
});
