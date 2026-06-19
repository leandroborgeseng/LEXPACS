import { expect, test } from '@playwright/test';

test.describe('Headers de segurança (S11)', () => {
  test('gateway envia CSP e X-Frame-Options', async ({ request }) => {
    const response = await request.get('/clinica/login');
    expect(response.status()).toBeLessThan(400);
    const headers = response.headers();
    expect(headers['x-content-type-options']).toBe('nosniff');
    expect(headers['x-frame-options']).toBe('SAMEORIGIN');
    expect(headers['content-security-policy']).toContain("default-src 'self'");
  });
});

test.describe('Rate limit login (S10)', () => {
  test('muitas tentativas inválidas retornam 429', async ({ request }) => {
    let saw429 = false;
    for (let i = 0; i < 25; i += 1) {
      const response = await request.post('/clinica-api/auth/clinical/login', {
        data: { username: 'invalid', password: 'invalid', next: '/viewer/' },
      });
      if (response.status() === 429) {
        saw429 = true;
        break;
      }
    }
    expect(saw429).toBeTruthy();
  });
});
