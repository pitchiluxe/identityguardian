import { test, expect } from '@playwright/test';
import { open, signIn } from './helpers';

test('learner completes the group-management lab in an isolated environment', async ({ page }) => {
  test.setTimeout(120_000);
  await signIn(page, 'lee');
  await open(page, 'Labs');
  await page.locator('.metric').filter({ hasText: 'Group management' }).getByRole('button', { name: 'Start attempt' }).click();
  await expect(page.getByRole('heading', { name: 'Group management' })).toBeVisible({ timeout: 30000 });
  await page.getByRole('button', { name: 'Hint 1 of 3' }).click();
  await expect(page.getByText(/Hint 1 · concept/)).toBeVisible();
  await page.getByRole('textbox', { name: 'Lab action' }).fill(JSON.stringify({ type: 'add_membership', identity: 'idn-sofia', group: 'grp-finance-analysts', justification: 'Cross-team project PRJ-9' }));
  await page.getByRole('button', { name: 'Apply action' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Action applied to your lab' })).toBeVisible();
  await page.getByRole('button', { name: 'Submit for grading' }).click();
  await expect(page.getByText(/PASSED · 100\/100/)).toBeVisible();
  await page.getByRole('button', { name: 'Explore this lab environment' }).click();
  await open(page, 'Identities');
  await expect(page.getByRole('button', { name: 'Sofia Rossi' })).toBeVisible();
});
