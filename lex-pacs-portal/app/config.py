from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # V1: Orthanc somente por variável de ambiente (ORTHANC_URL, ORTHANC_USERNAME, ORTHANC_PASSWORD)
    orthanc_url: str = ""
    orthanc_username: str = ""
    orthanc_password: str = ""
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
    clinical_session_hours: int = 12  # teto absoluto; inatividade em session_idle_minutes
    lex_pacs_version: str = "0.7.0"
    backup_status_path: str = "/lex-backups/latest-status.json"
    backup_retention_days: int = 14
    backup_retention_daily: int = 7
    backup_retention_weekly: int = 4
    backup_interval_hours: int = 24
    login_rate_limit_attempts: int = 20
    login_rate_limit_window_seconds: int = 60
    # Usuários locais (U1–U5) — sem Keycloak
    local_users_db_path: str = "/lex-data/users.db"
    # Índice de busca da lista de exames (só metadados, sem pixel). Vazio = ao lado do users.db.
    worklist_index_path: str = ""
    lex_admin_user: str = ""
    lex_admin_password: str = ""
    password_min_length: int = 10
    login_max_failures: int = 5
    login_lockout_minutes: int = 15
    session_idle_minutes: int = 30
    # V2/V4: Orthanc externo (prefeitura) — o portal não altera config/plugins/dados dele
    orthanc_external_readonly: bool = True
    hl7_orm_enabled: bool | None = None
    # LD1–LD5: aba/API de laudos. Ausente => False (oculto para todos; nenhum dado é apagado).
    lex_laudos_habilitado: bool = False
    hl7_orm_port: int = 2575
    hl7_orm_auto_sync: bool | None = None

    @property
    def orthanc_auth(self) -> tuple[str, str] | None:
        if self.orthanc_username:
            return (self.orthanc_username, self.orthanc_password)
        return None


settings = Settings()
