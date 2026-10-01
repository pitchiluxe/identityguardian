import { expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import { readFileSync } from 'node:fs';

type Person = { username: string; password: string };
const people = JSON.parse(readFileSync('.local/bootstrap.json', 'utf8')) as Person[];

/** Signs in through the real local Keycloak with SYNTHETIC generated credentials. */
export async function signIn(page: Page, username: string) {
  const account = people.find(p => p.username === username)!;
  await page.goto('/api/v1/auth/login');
  await page.locator('#username').fill(account.username);
  await page.locator('#password').fill(account.password);
  await page.locator('#kc-login').click();
  await expect(page.getByRole('heading', { name: 'Your identity workspace' })).toBeVisible({ timeout: 20000 });
}

export async function open(page: Page, name: string) {
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name, exact: true }).click();
  await expect(page.getByRole('heading', { level: 1, name })).toBeVisible();
}
