import {
  getClinicalBearerHeader,
  setClinicalSessionToken,
} from './lexClinicalSession';

export function configureLexClinicalAuth(userAuthenticationService: {
  setServiceImplementation: (impl: Record<string, unknown>) => void;
}): void {
  userAuthenticationService.setServiceImplementation({
    getAuthorizationHeader: () => getClinicalBearerHeader(),
  });
}

/** Obtém Bearer a partir do cookie de sessão (login OIDC ou local). */
export async function bootstrapClinicalDicomAuth(userAuthenticationService: {
  setServiceImplementation: (impl: Record<string, unknown>) => void;
}): Promise<void> {
  try {
    const response = await fetch('/clinica-api/auth/clinical/session', {
      credentials: 'include',
    });
    if (response.ok) {
      const data = await response.json();
      if (data?.access_token) {
        setClinicalSessionToken(data.access_token);
      }
    }
  } catch {
    /* viewer pode redirecionar para login depois */
  }
  configureLexClinicalAuth(userAuthenticationService);
}
