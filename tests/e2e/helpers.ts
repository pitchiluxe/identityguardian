import { expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import { createHmac } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';

type Person = { username: string; password: string; totp_seed?: string };
// Shared across Playwright worker processes (setup and test projects run separately).
const USED = '.local/e2e-totp-windows.json';
const usedWindows = {
  get: (u: string) => (existsSync(USED) ? JSON.parse(readFileSync(USED, 'utf8')) : {})[u] as number | undefined,
  set: (u: string, w: number) => writeFileSync(USED, JSON.stringify({ ...(existsSync(USED) ? JSON.parse(readFileSync(USED, 'utf8')) : {}), [u]: w })),
};
const people = JSON.parse(readFileSync('.local/bootstrap.json', 'utf8')) as Person[];

/** RFC 6238 TOTP (SHA-1, 6 digits, 30 s) for SYNTHETIC local test users only.
 *  Keycloak keys the HMAC with the stored secret's UTF-8 bytes. */
export function totp(seed: string, at = Date.now()) {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(at / 30000)));
  const mac = createHmac('sha1', Buffer.from(seed, 'utf8')).update(counter).digest();
  const offset = mac[mac.length - 1] & 0xf;
  return ((mac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).toString().padStart(6, '0');
}

/** Signs in through the real local Keycloak with SYNTHETIC generated credentials (and TOTP). */
export async function signIn(page: Page, username: string) {
  const account = people.find(p => p.username === username)!;
  await page.goto('/api/v1/auth/login');
  await page.locator('#username').fill(account.username);
  await page.locator('#password').fill(account.password);
  await page.locator('#kc-login').click();
  if (account.totp_seed) {
    // Keycloak rejects a code reused within its window, so wait for a fresh one if needed.
    let window = Math.floor(Date.now() / 30000);
    if (usedWindows.get(username) === window) {
      await page.waitForTimeout((window + 1) * 30000 - Date.now() + 500);
      window = Math.floor(Date.now() / 30000);
    }
    usedWindows.set(username, window);
    await page.locator('#otp').fill(totp(account.totp_seed));
    await page.locator('#kc-login').click();
  }
  await expect(page.getByRole('heading', { name: 'Your identity workspace' })).toBeVisible({ timeout: 20000 });
}

export async function open(page: Page, name: string) {
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name, exact: true }).click();
  await expect(page.getByRole('heading', { level: 1, name })).toBeVisible();
}
