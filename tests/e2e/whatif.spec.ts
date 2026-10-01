import { test, expect } from '@playwright/test';
import { open, signIn } from './helpers';

test('what-if removal of Erick Finance-Legacy shows loss, resolved finding and unchanged base', async ({ page }) => {
  await signIn(page, 'casey');
  await open(page, 'What-if simulator');
  await page.getByRole('combobox', { name: 'Simulation identity' }).selectOption({ label: 'Erick Mensah' });
  await page.getByRole('combobox', { name: 'Grant to remove' }).selectOption({ label: 'User member of group → Finance-Legacy (TKT-1042)' });
  await page.getByRole('button', { name: 'Run simulation' }).click();
  await expect(page.getByText('Unchanged (immutable overlay)')).toBeVisible();
  await expect(page.getByText('Payroll · SIMULATED · Manage payroll configuration').first()).toBeVisible();
  await expect(page.getByText(/Resolved: Erick Mensah retains Finance-Legacy/)).toBeVisible();
  await page.getByRole('button', { name: 'Create change proposal' }).click();
  await expect(page.getByText('DRAFT', { exact: true }).first()).toBeVisible();
  await page.getByRole('button', { name: 'Simulate' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Simulation recorded' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Bound simulation' })).toBeVisible();
});
