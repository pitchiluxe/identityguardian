import { test, expect } from '@playwright/test';
import { open, signIn } from './helpers';

test('time machine shows Erick payroll access on 2026-05-01 and replays a snapshot', async ({ page }) => {
  await signIn(page, 'morgan');
  await open(page, 'Time machine');
  await page.getByRole('combobox', { name: 'History identity' }).selectOption({ label: 'Erick Mensah' });
  await page.getByRole('textbox', { name: 'History effective at' }).fill('2026-05-01T12:00');
  await expect(page.getByText(/As known now \(same effective time\)/)).toBeVisible();
  await expect(page.getByText('Payroll · SIMULATED · Manage payroll configuration').first()).toBeVisible();
  await page.getByRole('button', { name: 'Snapshot this view' }).click();
  await page.getByRole('button', { name: /Replay/ }).first().click();
  await expect(page.getByText('MATCH', { exact: true })).toBeVisible();
});
