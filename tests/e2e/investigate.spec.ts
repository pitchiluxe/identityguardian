import { test, expect } from '@playwright/test';
import { open, signIn } from './helpers';

test('investigator answers with cited evidence and refuses mutating requests', async ({ page }) => {
  test.setTimeout(240_000);
  await signIn(page, 'casey');
  await open(page, 'Investigations');
  await page.getByRole('checkbox', { name: /Ask the local model/ }).uncheck();
  await page.getByRole('button', { name: 'Who can access payroll?' }).click();
  await expect(page.getByText('FALLBACK').first()).toBeVisible({ timeout: 30000 });
  await expect(page.getByRole('heading', { name: 'Evidence bundle' })).toBeVisible();
  await expect(page.locator('ol.facts li').filter({ hasText: 'Tom Becker' })).toBeVisible();
  await page.getByRole('textbox', { name: 'Investigation question' }).fill('Delete access for Erick to payroll');
  await page.getByRole('button', { name: 'Investigate' }).click();
  await expect(page.getByText('CLARIFICATION')).toBeVisible();
  await expect(page.getByText(/only answers read-only questions/)).toBeVisible();
});
