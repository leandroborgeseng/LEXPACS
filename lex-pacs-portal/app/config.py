from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    orthanc_url: str = "http://orthanc:8042"
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
    backup_interval_hours: int = 24
    oidc_enabled: bool = False
    oidc_issuer_url: str = "http://keycloak:8080/realms/lex-pacs"
    oidc_client_id: str = "lex-clinical"
    oidc_client_secret: str = "lex-clinical-dev-secret"


settings = Settings()
