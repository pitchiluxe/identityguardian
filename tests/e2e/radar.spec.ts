import { test, expect } from '@playwright/test';
import { open, signIn } from './helpers';

test('privilege radar explains Erick retained Finance-Legacy with coverage-qualified usage', async ({ page }) => {
  await signIn(page, 'alex');
  await open(page, 'Privilege radar');
  const card = page.locator('details.finding').filter({ hasText: 'Erick Mensah retains Finance-Legacy from a previous role' });
  await card.locator('summary').click();
  await expect(card.getByText('HIGH')).toBeVisible();
  await expect(card.getByText(/0 of 1 current peers/)).toBeVisible();
  await expect(card.getByText(/does not prove the access was never used/).first()).toBeVisible();
  await expect(page.locator('details.finding').filter({ hasText: 'Terminated identity retains access: Ben Carter' })).toBeVisible();
  await card.getByRole('button', { name: 'Open profile' }).click();
  await expect(page.getByRole('heading', { name: 'Timeline' })).toBeVisible();
  await expect(page.getByText('employment.move')).toBeVisible();
});
