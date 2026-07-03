import { configureLexClinicalAuth } from './lexClinicalDicomAuth';
import { clearClinicalSessionToken } from './lexClinicalSession';

export async function lexClinicalLogout(): Promise<void> {
  try {
    await fetch('/clinica-api/auth/clinical/logout', {
      method: 'POST',
      credentials: 'include',
    });
  } finally {
    clearClinicalSessionToken();
    const next = window.location.pathname + window.location.search;
    window.location.href = `/clinica/login?next=${encodeURIComponent(next)}`;
  }
}
