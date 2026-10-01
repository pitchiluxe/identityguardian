import { test, expect } from '@playwright/test';
import { open, signIn } from './helpers';

test('mover plan for Erick recommends removing Finance-Legacy with evidence', async ({ page }) => {
  await signIn(page, 'casey');
  await open(page, 'Lifecycle');
  await page.getByRole('row').filter({ hasText: 'Erick Mensah' }).getByRole('button', { name: 'Move' }).click();
  const remove = page.locator('.finding').filter({ hasText: 'Remove Finance-Legacy' });
  await expect(remove.getByText('REMOVE', { exact: true })).toBeVisible();
  await expect(remove.getByText(/TKT-1042/)).toBeVisible();
  await expect(page.locator('.finding').filter({ hasText: 'Retain HelpDesk-L2' })).toBeVisible();
  const leaver = page.getByRole('button', { name: 'All events' });
  await leaver.click();
  await page.getByRole('row').filter({ hasText: 'Ben Carter' }).getByRole('button', { name: 'Leave' }).click();
  await expect(page.getByText(/UNKNOWN: the sandbox source does not expose sessions/)).toBeVisible();
});
