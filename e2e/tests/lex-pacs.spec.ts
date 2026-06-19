import { expect, test } from '@playwright/test';

const clinicUser = process.env.CLINIC_USER || 'clinica';
const clinicPass = process.env.CLINIC_PASS || 'lexclinica2024';

test.describe('Login clínico → worklist', () => {
  test('credenciais válidas abrem o viewer', async ({ page }) => {
    await page.goto('/clinica/login?next=/viewer/');
    await page.locator('#username').fill(clinicUser);
    await page.locator('#password').fill(clinicPass);
    await page.locator('#login-btn').click();
    await page.waitForURL(/\/viewer\/?/, { timeout: 30_000 });
    await expect(page).toHaveTitle(/LEX PACS/i);
    await expect(page.locator('body')).toContainText(/study|exame|lista|list/i, {
      timeout: 30_000,
    });
  });
});

test.describe('Portal paciente', () => {
  test('página de login carrega', async ({ page }) => {
    await page.goto('/paciente/');
    await expect(page.locator('.logo-lex')).toBeVisible();
    await expect(page.locator('#login-form')).toBeVisible();
  });
});

test.describe('Tema', () => {
  test('alternância claro/escuro no portal', async ({ page }) => {
    await page.goto('/paciente/');
    const toggle = page.locator('[data-theme-toggle]');
    await expect(toggle).toBeVisible();
    const themeBefore = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
    await toggle.click();
    const themeAfter = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
    expect(themeAfter).not.toBe(themeBefore);
  });
});
