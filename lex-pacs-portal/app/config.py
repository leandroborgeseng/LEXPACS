from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    orthanc_url: str = "http://server:8042"
    ohif_viewer_url: str = "http://localhost:3000"
    jwt_secret: str = "change-me-in-production"
    jwt_expire_hours: int = 8
    viewer_token_expire_minutes: int = 30
    portal_fallback_code: str = ""
    cookie_secure: bool = False
    orthanc_config_path: str = "/orthanc-config/orthanc.json"
    reports_data_path: str = "/lex-reports"
    audit_data_path: str = "/lex-audit"
    orthanc_worklist_path: str = "/var/lib/orthanc/worklists"
    clinical_htpasswd_path: str = "/etc/lex-pacs/htpasswd"
    clinical_session_hours: int = 12
    lex_pacs_version: str = "0.7.0"
    backup_status_path: str = "/lex-backups/latest-status.json"
    backup_retention_days: int = 14
    backup_retention_daily: int = 7
    backup_retention_weekly: int = 4
    backup_interval_hours: int = 24
    login_rate_limit_attempts: int = 20
    login_rate_limit_window_seconds: int = 60
    oidc_enabled: bool = False
    oidc_issuer_url: str = "http://auth:8080/auth/realms/lex-pacs"
    oidc_public_issuer_url: str = "http://localhost:3000/auth/realms/lex-pacs"
    oidc_client_id: str = "lex-clinical"
    oidc_client_secret: str = "lex-clinical-dev-secret"
    clinical_local_auth_enabled: bool = True
    clinical_bootstrap_user: str = ""
    clinical_bootstrap_password: str = ""


    @property
    def oidc_redirect_uri(self) -> str:
        base = self.ohif_viewer_url.rstrip("/")
        return f"{base}/clinica-api/auth/clinical/oidc/callback"


settings = Settings()
