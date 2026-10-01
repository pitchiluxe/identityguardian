import { test, expect } from '@playwright/test';
import { signIn } from './helpers';

test('approver session carries verified pwd+otp assurance from the identity provider', async ({ page }) => {
  await signIn(page, 'jordan');
  const session = await (await page.request.get('/api/v1/session')).json();
  expect(session.amr).toEqual(expect.arrayContaining(['pwd', 'otp']));
});

test('password-only session does not claim MFA', async ({ page }) => {
  await signIn(page, 'sam');
  const session = await (await page.request.get('/api/v1/session')).json();
  expect(session.amr).not.toContain('otp');
});
