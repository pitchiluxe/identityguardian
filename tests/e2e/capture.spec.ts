import { test } from '@playwright/test';
import { open, signIn } from './helpers';

// Captures real screenshots of the running build for documentation. Run explicitly with CAPTURE=1.
test.skip(!process.env.CAPTURE, 'Set CAPTURE=1 to record documentation screenshots');
const shots = process.env.CAPTURE_DIR || 'docs/screenshots';

test('capture current workspace pages', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await signIn(page, 'alex');
  await page.screenshot({ path: `${shots}/dashboard.png`, fullPage: true });
  for (const name of (process.env.CAPTURE_PAGES || 'Identity graph').split(',')) {
    await open(page, name);
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${shots}/${name.toLowerCase().replaceAll(' ', '-')}.png`, fullPage: true });
  }
});
