export const LEX_CLINICAL_TOKEN_KEY = 'lex_clinical_token';

export function getClinicalSessionToken(): string {
  try {
    return sessionStorage.getItem(LEX_CLINICAL_TOKEN_KEY) || '';
  } catch {
    return '';
  }
}

export function setClinicalSessionToken(token: string): void {
  try {
    if (token) {
      sessionStorage.setItem(LEX_CLINICAL_TOKEN_KEY, token);
    }
  } catch {
    /* ignore */
  }
}

export function clearClinicalSessionToken(): void {
  try {
    sessionStorage.removeItem(LEX_CLINICAL_TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

export function getClinicalBearerHeader(): Record<string, string> {
  const token = getClinicalSessionToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
