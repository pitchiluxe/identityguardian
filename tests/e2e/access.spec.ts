import { test, expect } from '@playwright/test';
import { open, signIn } from './helpers';

test('profile explains Erick payroll access through the nested legacy route', async ({ page }) => {
  await signIn(page, 'alex');
  await open(page, 'Access');
  await page.getByRole('combobox', { name: 'Identity' }).selectOption({ label: 'Erick Mensah (employee)' });
  const payroll = page.locator('details').filter({ hasText: 'Payroll · SIMULATED · Manage payroll configuration' });
  await expect(payroll.getByText('ALLOW').first()).toBeVisible();
  const lineage = payroll.getByLabel('Access lineage').first();
  for (const hop of ['Finance-Legacy', 'ERP-Operators', 'ERP Application Administrator', 'Manage payroll configuration']) {
    await expect(lineage.getByText(hop, { exact: true })).toBeVisible();
  }
  await expect(lineage.getByText('TKT-1042')).toBeVisible();
  await expect(payroll.getByText(/No observed use during coverage/)).toBeVisible();
  await payroll.getByRole('button', { name: 'Who else can access Payroll · SIMULATED?' }).click();
  await expect(page.getByRole('heading', { name: 'Who can access Payroll · SIMULATED' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Tom Becker' })).toBeVisible();
});

test('viewer is denied effective access', async ({ page }) => {
  await signIn(page, 'sam');
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name: 'Access', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Restricted to authorized roles' })).toBeVisible();
});
