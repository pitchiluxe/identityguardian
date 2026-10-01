import { test, expect } from '@playwright/test';
import { open, signIn } from './helpers';

test('policy is validated, tested, simulated, independently approved and activated', async ({ browser }) => {
  test.setTimeout(150_000);
  const admin = await browser.newPage();
  await signIn(admin, 'alex');
  await open(admin, 'Policies');
  const name = `Contractor GA rule ${Date.now()}`;
  const definition = (await admin.getByRole('textbox', { name: 'Policy definition' }).inputValue()).replace('No permanent Global Administrator for contractors', name);
  await admin.getByRole('textbox', { name: 'Policy definition' }).fill(definition);
  await admin.getByRole('button', { name: 'Validate and save draft' }).click();
  const card = admin.locator('details.finding').filter({ hasText: name });
  await card.getByRole('button', { name: 'Run tests' }).click();
  await expect(card.getByText('PASS').first()).toBeVisible();
  await card.getByRole('button', { name: 'Simulate scope' }).click();
  await expect(card.getByText('Grace Hall → Global Administrator')).toBeVisible();
  const approver = await browser.newPage();
  await signIn(approver, 'jordan');
  await open(approver, 'Policies');
  await approver.locator('details.finding').filter({ hasText: name }).getByRole('button', { name: 'Approve exact digest' }).click();
  await expect(approver.getByRole('status').filter({ hasText: 'Approved' })).toBeVisible();
  await admin.getByRole('button', { name: 'Refresh' }).click();
  await admin.locator('details.finding').filter({ hasText: name }).getByRole('button', { name: 'Activate' }).click();
  await expect(admin.locator('details.finding').filter({ hasText: name }).getByText('ACTIVE').first()).toBeVisible();
  await Promise.all([admin.close(), approver.close()]);
});
