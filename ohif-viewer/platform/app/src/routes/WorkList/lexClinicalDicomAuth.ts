import { getClinicalBearerHeader } from './lexClinicalSession';

export function configureLexClinicalAuth(userAuthenticationService: {
  setServiceImplementation: (impl: Record<string, unknown>) => void;
}): void {
  userAuthenticationService.setServiceImplementation({
    getAuthorizationHeader: () => getClinicalBearerHeader(),
  });
}
