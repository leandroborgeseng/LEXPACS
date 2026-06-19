export type ClinicalPermissions = {
  is_admin: boolean;
  can_sign: boolean;
  can_draft: boolean;
  can_release: boolean;
  can_admin: boolean;
  role: string;
  role_label: string;
};

export type ClinicalProfile = {
  username: string;
  groups: string[];
  auth_method: string;
  permissions: ClinicalPermissions;
};

export async function fetchClinicalProfile(): Promise<ClinicalProfile | null> {
  try {
    const response = await fetch('/clinica-api/auth/clinical/me', { credentials: 'include' });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as ClinicalProfile;
  } catch {
    return null;
  }
}
