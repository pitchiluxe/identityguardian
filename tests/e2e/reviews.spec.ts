import { test, expect } from '@playwright/test';
import { open, signIn } from './helpers';

test('admin starts a campaign and the assigned reviewer records REMOVE as a proposal', async ({ page, browser }) => {
  const name = `Retained access ${Date.now()}`;
  await signIn(page, 'alex');
  await open(page, 'Access reviews');
  await page.getByRole('textbox', { name: 'Name' }).fill(name);
  await page.getByRole('combobox', { name: 'Reviewer' }).selectOption({ label: 'Riley Contoso' });
  await page.getByRole('button', { name: 'Create campaign' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'evidence-backed items' })).toBeVisible();

  const reviewer = await browser.newPage();
  await signIn(reviewer, 'riley');
  await open(reviewer, 'Access reviews');
  await reviewer.getByRole('button', { name }).click();
  const item = reviewer.locator('details.finding').filter({ hasText: 'Erick Mensah retains Finance-Legacy' });
  await expect(item.getByText('Recommends REMOVE')).toBeVisible();
  await expect(item.getByText(/Uncertainty:/)).toBeVisible();
  await item.getByRole('combobox', { name: 'Decision' }).selectOption('REMOVE');
  await item.getByRole('textbox', { name: 'Justification' }).fill('Finance-Legacy is not needed after the move to IT Support.');
  await item.getByRole('button', { name: 'Record decision' }).click();
  await expect(item.getByText(/Decided REMOVE by Riley Contoso/)).toBeVisible();
  await expect(item.getByText(/change proposal/)).toBeVisible();
  await expect(item.getByText('(DRAFT)')).toBeVisible();
  await reviewer.close();
});
