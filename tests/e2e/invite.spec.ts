import { test, expect } from '@playwright/test';
import { signIn, open, totp } from './helpers';

test('invitee registers own credentials and lands with the invited role', async ({ page, browser }) => {
  await signIn(page, 'alex');
  await open(page, 'Administration');
  const email = `e2e.${Date.now()}@example.org`;
  await page.getByLabel('Invite email').fill(email);
  await page.getByLabel('Invite role').selectOption('viewer');
  await page.getByLabel('Invite justification').fill('SYNTHETIC end-to-end invitee');
  await page.getByRole('button', { name: 'Create invite' }).click();
  const link = await page.locator('.notice code').innerText();
  const invitee = await (await browser.newContext()).newPage();
  await invitee.goto(link);
  await invitee.getByRole('link', { name: 'Create account' }).click();
  const username = `e2e${Date.now()}`;
  await invitee.locator('#username').fill(username);
  await invitee.locator('#email').fill(email);
  await invitee.locator('#firstName').fill('Synthetic');
  await invitee.locator('#lastName').fill('Invitee');
  await invitee.locator('#password').fill('Synthetic-Pass-2026!');
  await invitee.locator('#password-confirm').fill('Synthetic-Pass-2026!');
  await invitee.getByRole('button', { name: /register/i }).click();
  await invitee.getByRole('link', { name: /unable to scan/i }).click();
  const seed = (await invitee.locator('#kc-totp-secret-key').innerText()).replace(/\s/g, '');
  // The displayed key is base32 of the secret's UTF-8 bytes; decode to the raw secret for totp().
  const raw = Buffer.from(base32Decode(seed)).toString('utf8');
  await invitee.locator('#totp').fill(totp(raw));
  await invitee.getByRole('button', { name: /submit/i }).click();
  await expect(invitee.getByRole('heading', { name: 'Your identity workspace' })).toBeVisible({ timeout: 20000 });
});

function base32Decode(s: string) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'; let bits = ''; const out: number[] = [];
  for (const c of s.replace(/=+$/, '').toUpperCase()) bits += alphabet.indexOf(c).toString(2).padStart(5, '0');
  for (let i = 0; i + 8 <= bits.length; i += 8) out.push(parseInt(bits.slice(i, i + 8), 2));
  return Uint8Array.from(out);
}
