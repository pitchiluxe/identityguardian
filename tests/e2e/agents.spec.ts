import { test, expect } from '@playwright/test';
import { open, signIn } from './helpers';

test('agent registry compares declared and effective scope and answers capability queries', async ({ page }) => {
  await signIn(page, 'sam');
  await open(page, 'AI agents');
  const support = page.locator('details.finding').filter({ hasText: 'Customer Support Assistant' });
  await expect(support.getByText('local-llm-support-v2')).toBeVisible();
  await expect(support.getByText('VALID')).toBeVisible();
  await expect(support.getByText(/customer-data \(Customer Data Store\)/)).toBeVisible();
  await page.getByRole('combobox', { name: 'Data class filter' }).selectOption('source-code');
  await expect(page.locator('details.finding')).toHaveCount(1);
  await expect(page.getByText('Code Review Agent')).toBeVisible();
});
