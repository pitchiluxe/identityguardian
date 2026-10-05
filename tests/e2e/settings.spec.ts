import { test, expect } from '@playwright/test';
import { open, signIn } from './helpers';

test('settings shows Ollama as the default and gates hosted providers behind the admin switch', async ({ page }) => {
  await signIn(page, 'alex');
  await open(page, 'Settings');
  await expect(page.getByRole('radio', { name: /Ollama/ })).toBeChecked();
  await expect(page.getByText(/Ollama is (running|not running)/)).toBeVisible();
  await expect(page.getByRole('radio', { name: /Claude/ })).toBeDisabled();
  await expect(page.getByRole('radio', { name: /ChatGPT/ })).toBeDisabled();
  await expect(page.getByText('Hosted AI providers are disabled for this organization')).toBeVisible();
  await expect(page.getByRole('checkbox', { name: 'Allow hosted AI providers for this organization' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'ollama.com/download' })).toBeVisible();
});
