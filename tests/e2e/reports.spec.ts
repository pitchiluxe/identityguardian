import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { open, signIn } from './helpers';

test('auditor generates a redacted privilege-creep report and downloads it', async ({ page }) => {
  await signIn(page, 'morgan');
  await open(page, 'Reports');
  await page.getByRole('combobox', { name: 'Report type' }).selectOption('privilege_creep');
  await page.getByRole('button', { name: 'Generate' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Report generated' })).toBeVisible();
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('link', { name: 'Download' }).first().click()]);
  const path = await download.path();
  const text = readFileSync(path, 'utf8');
  expect(text).toContain('# redaction: standard');
  expect(text).toContain('PRIOR_ROLE_RETAINED');
});
