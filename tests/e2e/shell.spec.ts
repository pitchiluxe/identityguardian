import { test, expect } from '@playwright/test';

test('signed out visitor sees honest foundation and sign in', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Know the identity. Understand the access.' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Sign in with your identity provider' })).toHaveAttribute('href', '/api/v1/auth/login');
  await expect(page.getByText('Local build · synthetic data')).toBeVisible();
});

test('mobile login remains accessible without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('link', { name: 'Sign in with your identity provider' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
