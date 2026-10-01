import { test, expect } from '@playwright/test';
import { open, signIn } from './helpers';

test('administrator loads synthetic sandbox, syncs and follows Erick provenance into the graph', async ({ page }) => {
  await signIn(page, 'alex');
  await open(page, 'Integrations');
  await expect(page.getByText('SYNTHETIC · sandbox connector')).toBeVisible();
  await page.getByRole('button', { name: 'Load synthetic fixture into sandbox source' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Sandbox source updated' })).toBeVisible();
  await page.getByRole('button', { name: 'Full authoritative sync' }).click();
  await expect(page.getByRole('status').filter({ hasText: /Sync (SUCCEEDED|PARTIAL)/ })).toBeVisible();
  await open(page, 'Identities');
  await page.getByRole('textbox', { name: 'Search identities' }).fill('Erick');
  await page.getByRole('button', { name: 'Erick Mensah' }).click();
  await expect(page.getByRole('heading', { name: 'Erick Mensah' })).toBeVisible();
  await expect(page.getByText('legacy_entitlement · TKT-1042')).toBeVisible();
  await expect(page.getByText('SYNTHETIC').first()).toBeVisible();
  await page.getByRole('button', { name: 'Open in graph' }).click();
  await expect(page.getByRole('img', { name: /Relationship graph around Erick Mensah/ })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'Finance-Legacy' }).first()).toBeVisible();
  await page.getByRole('button', { name: 'Finance-Legacy, group. Focus' }).click();
  await expect(page.getByRole('img', { name: /Relationship graph around Finance-Legacy/ })).toBeVisible();
});

test('viewer can explore but cannot seed or sync', async ({ page }) => {
  await signIn(page, 'sam');
  await open(page, 'Integrations');
  await expect(page.getByText('Your role can view sync history only.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Full authoritative sync' })).toHaveCount(0);
  await open(page, 'Identities');
  await expect(page.getByRole('button', { name: 'Erick Mensah' })).toBeVisible();
});
