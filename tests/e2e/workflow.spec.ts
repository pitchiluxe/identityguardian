import { test, expect } from '@playwright/test';
import { open, signIn } from './helpers';

// Multi-actor flows sign in three MFA users; allow more than the 30 s default.
test.describe.configure({ timeout: 150_000 });

test('DEMO: simulate, independent MFA approval, sandbox execution, history retained', async ({ browser }) => {
  // Investigator proposes and simulates removal of only Erick -> Finance-Legacy.
  const investigator = await browser.newPage();
  await signIn(investigator, 'casey');
  await open(investigator, 'What-if simulator');
  await investigator.getByRole('combobox', { name: 'Simulation identity' }).selectOption({ label: 'Erick Mensah' });
  await investigator.getByRole('combobox', { name: 'Grant to remove' }).selectOption({ label: 'User member of group → Finance-Legacy (TKT-1042)' });
  await investigator.getByRole('button', { name: 'Run simulation' }).click();
  await investigator.getByRole('button', { name: 'Create change proposal' }).click();
  await investigator.getByRole('button', { name: 'Simulate' }).click();
  await expect(investigator.getByRole('heading', { name: 'Bound simulation' })).toBeVisible();
  await investigator.getByRole('button', { name: 'Submit for approval' }).click();
  await expect(investigator.getByText(/Awaiting an independent approver/)).toBeVisible();
  const requestId = ((await investigator.getByTestId('change-id').textContent()) || '').replace('Request ', '').slice(0, 8);
  expect(requestId).toHaveLength(8);

  // Independent approver with MFA approves the exact digest.
  const approver = await browser.newPage();
  await signIn(approver, 'jordan');
  await open(approver, 'Change requests');
  await approver.getByRole('row').filter({ hasText: requestId }).getByRole('button').click();
  await expect(approver.getByText('Approve this exact proposal')).toBeVisible();
  await approver.getByRole('textbox', { name: 'Approval justification' }).fill('Simulation shows only Erick loses payroll configuration; no lockout.');
  await approver.getByRole('button', { name: 'Approve exact digest' }).click();
  await expect(approver.getByRole('status').filter({ hasText: 'Approved' })).toBeVisible();

  // A different operator with MFA executes in the sandbox; the worker confirms by read-back.
  const operator = await browser.newPage();
  await signIn(operator, 'quinn');
  await open(operator, 'Change requests');
  await operator.getByRole('row').filter({ hasText: requestId }).getByRole('button').click();
  await operator.getByRole('button', { name: /Execute in LAB sandbox/ }).click();
  await expect(operator.getByRole('status').filter({ hasText: 'Queued for sandbox execution' })).toBeVisible();
  await expect(operator.getByText('change.succeeded')).toBeVisible({ timeout: 30000 });

  // Current route gone; effective-time history at 2026-05-01 still shows it.
  await open(operator, 'Access');
  await operator.getByRole('combobox', { name: 'Identity' }).selectOption({ label: 'Erick Mensah (employee)' });
  await expect(operator.getByText(/Effective access · Erick Mensah/)).toBeVisible();
  await expect(operator.locator('details').filter({ hasText: 'Payroll · SIMULATED · Manage payroll configuration' })).toHaveCount(0);
  await operator.getByRole('textbox', { name: 'Effective at' }).fill('2026-05-01T12:00');
  await expect(operator.locator('details').filter({ hasText: 'Payroll · SIMULATED · Manage payroll configuration' })).toHaveCount(1);
  await Promise.all([investigator.close(), approver.close(), operator.close()]);
});

test('JIT request is approved by another approver and executed with native expiry', async ({ browser }) => {
  const requester = await browser.newPage();
  await signIn(requester, 'casey');
  await open(requester, 'JIT access');
  await requester.getByRole('combobox', { name: 'JIT identity' }).selectOption({ label: 'Maria Lopez' });
  await requester.getByRole('combobox', { name: 'JIT group' }).selectOption({ label: 'Security-Admins' });
  await requester.getByRole('textbox', { name: 'Justification' }).fill('INC-4411 containment review for one hour');
  await requester.getByRole('button', { name: 'Simulate and submit' }).click();
  await expect(requester.getByRole('status').filter({ hasText: 'submitted for independent approval' })).toBeVisible();
  const approver = await browser.newPage();
  await signIn(approver, 'jamie');
  await open(approver, 'JIT access');
  await approver.getByRole('button', { name: 'Maria Lopez → Security-Admins' }).first().click();
  await approver.getByRole('textbox', { name: 'Approval justification' }).fill('Incident containment, bounded to 60 minutes.');
  await approver.getByRole('button', { name: 'Approve exact digest' }).click();
  await expect(approver.getByRole('status').filter({ hasText: 'Approved' })).toBeVisible();
  const operator = await browser.newPage();
  await signIn(operator, 'quinn');
  await open(operator, 'JIT access');
  await operator.getByRole('button', { name: 'Maria Lopez → Security-Admins' }).first().click();
  await operator.getByRole('button', { name: /Execute in LAB sandbox/ }).click();
  await expect(operator.getByRole('status').filter({ hasText: 'Queued for sandbox execution' })).toBeVisible();
  await open(operator, 'JIT access');
  await expect(operator.getByRole('row').filter({ hasText: 'Maria Lopez → Security-Admins' }).filter({ hasText: 'ACTIVE' }).first()).toBeVisible({ timeout: 30000 });
  await Promise.all([requester.close(), approver.close(), operator.close()]);
});
