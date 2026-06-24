from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from .clinical_session import ClinicalUser
from .clinical_auth import require_admin, require_clinical_user
from .audit import list_events, log_event
from .mwl_scheduler import run_mwl_sync
from .mwl_sql import get_mwl_sql_config, get_mwl_sync_meta, save_mwl_sql_config
from .mwl_connector import execute_select, test_connection
from .mwl_fetch import fetch_mwl_source_rows
from .mwl_drivers import list_drivers, MWL_FIELDS
from .mwl_sync import list_mwl_entries, orthanc_mwl_plugin_enabled
from .lex_settings import (
    get_equipment,
    get_worklist_views,
    save_equipment,
    save_worklist_views,
)
from .backup_status import get_backup_status
from .backup_trigger import clear_backup_trigger, request_backup
from .hl7_orm import parse_orm_message, process_hl7_orm
from .hl7_mllp import restart_hl7_mllp_server
from .hl7_settings import get_hl7_config, get_hl7_stats, save_hl7_config
from .mpps_server import mpps_server_running, restart_mpps_server
from .mpps_settings import get_mpps_config, get_mpps_stats, save_mpps_config
from .qr_service import build_qr_status_payload, test_c_find_study
from .qr_settings import get_qr_config, save_qr_config
from .dicom_tls_service import (
    apply_dicom_tls_orthanc_settings,
    build_dicom_tls_status_payload,
    generate_dev_certificates,
    test_dicom_tls_echo,
)
from .dicom_tls_settings import save_dicom_tls_config
from .pacs_config import get_pacs_settings, update_server_settings
from .pacs_stats import collect_pacs_stats
from .portal_settings import get_portal_ops, save_portal_ops
from .migration_store import get_migration_status
from .migration_service import (
    pause_migration,
    reset_migration,
    run_migration_discovery,
    save_migration_settings,
    start_migration,
    test_migration_echo,
)
from .storage_service import (
    pause_storage_run,
    reset_storage_run,
    start_storage_run,
)
from .storage_store import get_storage_status, save_storage_config
from .storage_worker import kick_storage_worker
from .ad_settings import (
    ad_status_payload,
    get_ad_config,
    record_ad_sync_error,
    record_ad_sync_success,
    save_ad_config,
)
from .keycloak_admin import (
    KeycloakAdminError,
    apply_ad_config_to_keycloak,
    sync_ad_users_and_groups,
    test_ad_connection,
)

router = APIRouter(prefix="/api/admin/pacs", tags=["admin"])


class EquipmentItem(BaseModel):
    id: str | None = None
    aet: str = Field(min_length=1, max_length=16)
    host: str = Field(min_length=1, max_length=128)
    port: int = Field(default=104, ge=1, le=65535)
    description: str = Field(default="", max_length=64)
    modality: str = Field(default="", max_length=16)


class WorklistViewItem(BaseModel):
    id: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=48)
    modalities: list[str] = Field(default_factory=list)
    description: str = Field(default="", max_length=64)
    station_aet: str = Field(default="", max_length=16)


class PacsSettingsResponse(BaseModel):
    dicom_aet: str
    dicom_port: int
    name: str = "LEX PACS"
    dicom_check_called_aet: bool = True
    dicom_check_modality_host: bool = True
    dicom_restrict_inbound: bool = True
    registered_modality_count: int = 0
    dicom_inbound_open_warning: bool = False
    storage_directory: str = ""
    postgresql_index: bool = False
    ingest_transcoding: str = ""
    ingest_transcoding_options: list[str] = Field(default_factory=list)
    worklists_enabled: bool = True
    worklists_filter_issuer_aet: bool = False


class UpdateServerSettingsRequest(BaseModel):
    dicom_aet: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=1, max_length=64)
    dicom_check_called_aet: bool = True
    dicom_check_modality_host: bool = True
    dicom_restrict_inbound: bool = True
    ingest_transcoding: str = ""
    worklists_enabled: bool = True
    worklists_filter_issuer_aet: bool = False


class UpdateAetRequest(BaseModel):
    dicom_aet: str = Field(min_length=1, max_length=16)


class UpdateSettingsResponse(BaseModel):
    dicom_aet: str
    dicom_port: int
    name: str
    dicom_check_called_aet: bool
    dicom_check_modality_host: bool
    dicom_restrict_inbound: bool
    registered_modality_count: int = 0
    dicom_inbound_open_warning: bool = False
    restarted: bool
    message: str


class EquipmentListResponse(BaseModel):
    items: list[EquipmentItem]


class WorklistViewsResponse(BaseModel):
    views: list[WorklistViewItem]


class ModalityRouteItem(BaseModel):
    modality: str = Field(min_length=1, max_length=16)
    station_aet: str = Field(default="", max_length=16)


class MwlSqlConfigResponse(BaseModel):
    enabled: bool = True
    driver: str = "postgresql"
    mode: str = "table"
    host: str
    port: int
    database: str
    username: str
    password_env: str = "POSTGRES_PASSWORD"
    table: str = "lex_mwl_schedule"
    custom_sql: str = ""
    field_mapping: dict[str, str] = Field(default_factory=dict)
    modality_filter: list[str] = Field(default_factory=list)
    modality_routes: list[ModalityRouteItem] = Field(default_factory=list)
    sync_interval_minutes: int = 5
    password_configured: bool = False
    available_drivers: list[dict] = Field(default_factory=list)


class MwlSyncResponse(BaseModel):
    removed: int
    synced: int
    files: list[str]
    worklist_dir: str
    plugin_enabled: bool = False
    last_at: str = ""
    last_actor: str = ""


class MwlStatusResponse(BaseModel):
    sql: MwlSqlConfigResponse
    sync: dict
    plugin_enabled: bool = False
    entries_total: int = 0


class MwlEntry(BaseModel):
    accession_number: str
    patient_id: str
    patient_name: str
    modality: str
    station_aet: str
    procedure_description: str
    scheduled_date: str


class MwlEntriesResponse(BaseModel):
    entries: list[MwlEntry]


class MwlSqlPreviewResponse(BaseModel):
    columns: list[str]
    raw_rows: list[dict]
    mapped_entries: list[MwlEntry]


class AuditEvent(BaseModel):
    timestamp: str
    event: str
    actor: str


class AuditListResponse(BaseModel):
    events: list[dict]


class StatsBucketItem(BaseModel):
    label: str
    count: int


class StatsModalityItem(BaseModel):
    modality: str
    studies: int
    series: int


class StatsDiskItem(BaseModel):
    label: str
    bytes: int
    mb: float


class PacsStatsResponse(BaseModel):
    patients: int
    studies: int
    series: int
    instances: int
    studies_by_modality: list[StatsModalityItem]
    study_date_age: list[StatsBucketItem]
    received_age: list[StatsBucketItem]
    disk: list[StatsDiskItem]
    disk_total_bytes: int
    disk_total_mb: float
    generated_at: str


class BackupStatusResponse(BaseModel):
    configured: bool
    success: bool
    last_at: str
    last_path: str
    lex_pacs_version: str
    backup_root: str
    retention_days: int
    retention_daily: int
    retention_weekly: int
    interval_hours: int
    error: str = ""


class Hl7ConfigResponse(BaseModel):
    enabled: bool = True
    listen_host: str = "0.0.0.0"
    listen_port: int = 2575
    auto_sync: bool = True
    map_modality_to_station: bool = True
    default_station_aet: str = ""
    sending_application: str = "LEXPACS"
    sending_facility: str = "LEX"


class Hl7StatsResponse(BaseModel):
    messages_total: int = 0
    last_at: str = ""
    last_accession: str = ""
    last_control: str = ""
    last_message_type: str = ""
    last_error: str = ""


class Hl7StatusResponse(BaseModel):
    config: Hl7ConfigResponse
    stats: Hl7StatsResponse


class Hl7TestRequest(BaseModel):
    message: str = Field(min_length=10)
    apply: bool = True


class Hl7TestResponse(BaseModel):
    parsed: dict
    applied: bool = False
    result: dict | None = None


class MppsConfigResponse(BaseModel):
    enabled: bool = True
    listen_host: str = "0.0.0.0"
    listen_port: int = 4243
    aet: str = "LEXMPPS"
    auto_complete_mwl: bool = True
    complete_on_discontinued: bool = False


class MppsStatsResponse(BaseModel):
    messages_total: int = 0
    completed_total: int = 0
    mwl_removed_total: int = 0
    last_at: str = ""
    last_accession: str = ""
    last_status: str = ""
    last_actor: str = ""
    last_error: str = ""


class MppsStatusResponse(BaseModel):
    config: MppsConfigResponse
    stats: MppsStatsResponse
    server_running: bool = False


class MppsSimulateRequest(BaseModel):
    accession_number: str = Field(min_length=1, max_length=32)


class MppsSimulateResponse(BaseModel):
    applied: bool
    accession: str = ""
    mwl_deleted: bool = False
    worklist_file_removed: bool = False
    reason: str = ""


class QrConsumerItem(BaseModel):
    key: str
    aet: str
    host: str
    allow_find: bool = False
    allow_move: bool = False
    allow_get: bool = False


class QrOrthancStatus(BaseModel):
    query_retrieve_size: int = 100
    dicom_always_allow_move: bool = False
    dicom_always_allow_get: bool = False
    dicom_always_allow_find: bool = False


class QrConfigResponse(BaseModel):
    query_retrieve_size: int = 100
    smoke_consumer_aet: str = "LEXQR"
    smoke_consumer_host: str = "portal"


class QrStatsResponse(BaseModel):
    last_at: str = ""
    last_actor: str = ""
    last_find_count: int = 0
    last_error: str = ""
    last_success: bool = False


class QrStatusResponse(BaseModel):
    dicom_aet: str
    dicom_port: int
    orthanc: QrOrthancStatus
    config: QrConfigResponse
    stats: QrStatsResponse
    consumers: list[QrConsumerItem] = Field(default_factory=list)
    consumer_count: int = 0
    qr_ready: bool = False


class QrTestResponse(BaseModel):
    success: bool
    find_count: int = 0
    calling_aet: str = ""
    called_aet: str = ""
    host: str = ""
    port: int = 4242
    error: str = ""


class DicomTlsConfigResponse(BaseModel):
    enabled: bool = False
    remote_certificate_required: bool = False
    smoke_consumer_aet: str = "LEXTLS"
    min_protocol_version: int = 0


class DicomTlsOrthancStatus(BaseModel):
    enabled: bool = False
    remote_certificate_required: bool = False
    min_protocol_version: int = 0
    certificate: str = ""
    private_key: str = ""
    trusted_certificates: str = ""
    configured_enabled: bool = False


class DicomTlsCertificatesStatus(BaseModel):
    ca_present: bool = False
    server_present: bool = False
    trusted_present: bool = False
    client_present: bool = False
    ready: bool = False
    directory: str = ""
    server_certificate: str = ""
    server_private_key: str = ""
    trusted_certificates: str = ""
    client_certificate: str = ""


class DicomTlsStatsResponse(BaseModel):
    last_at: str = ""
    last_actor: str = ""
    last_success: bool = False
    last_error: str = ""
    generated_at: str = ""
    generated_by: str = ""


class DicomTlsStatusResponse(BaseModel):
    config: DicomTlsConfigResponse
    stats: DicomTlsStatsResponse
    orthanc: DicomTlsOrthancStatus
    certificates: DicomTlsCertificatesStatus
    dicom_aet: str
    dicom_port: int
    tls_ready: bool = False


class DicomTlsTestResponse(BaseModel):
    success: bool
    calling_aet: str = ""
    called_aet: str = ""
    host: str = ""
    port: int = 4242
    error: str = ""
    return_code: int | None = None


class PortalOpsResponse(BaseModel):
    backup_interval_hours: int = 24
    backup_retention_daily: int = 7
    backup_retention_weekly: int = 4
    backup_retention_days: int = 14
    login_rate_limit_attempts: int = 20
    login_rate_limit_window_seconds: int = 60


class MigrationSource(BaseModel):
    label: str = ""
    aet: str = Field(default="", max_length=16)
    host: str = Field(default="", max_length=128)
    port: int = Field(default=104, ge=1, le=65535)


class MigrationFilters(BaseModel):
    study_date_from: str = ""
    study_date_to: str = ""
    patient_id: str = ""
    modality: str = ""


class MigrationConfigRequest(BaseModel):
    source: MigrationSource
    filters: MigrationFilters = Field(default_factory=MigrationFilters)
    batch_size: int = Field(default=1, ge=1, le=10)
    pause_seconds: int = Field(default=2, ge=0, le=300)
    skip_existing: bool = True


class MigrationStats(BaseModel):
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    instances_imported: int = 0


class MigrationStatusResponse(BaseModel):
    config: dict
    status: str = "idle"
    cursor: int = 0
    queue_total: int = 0
    pending: int = 0
    progress_percent: float = 0.0
    stats: MigrationStats
    last_error: str = ""
    started_at: str = ""
    updated_at: str = ""
    last_study_uid: str = ""
    discovered_at: str = ""
    modality_key: str = "LEX_MIG_SRC"


class MigrationActionResponse(BaseModel):
    status: str
    message: str = ""
    discovered: int = 0
    queue_total: int = 0
    pending: int = 0


class StorageRuleItem(BaseModel):
    id: str = ""
    enabled: bool = True
    min_age_years: int = Field(default=2, ge=1, le=50)
    transfer_syntax: str = ""
    modalities: list[str] = Field(default_factory=list)


class TransferSyntaxOption(BaseModel):
    uid: str
    label: str


class StorageConfigRequest(BaseModel):
    enabled: bool = False
    run_interval_hours: int = Field(default=24, ge=1, le=168)
    batch_size: int = Field(default=5, ge=1, le=50)
    pause_seconds: int = Field(default=2, ge=0, le=300)
    rules: list[StorageRuleItem] = Field(default_factory=list)


class StorageStats(BaseModel):
    compressed: int = 0
    skipped: int = 0
    failed: int = 0
    instances: int = 0


class StorageStatusResponse(BaseModel):
    enabled: bool = False
    run_interval_hours: int = 24
    batch_size: int = 5
    pause_seconds: int = 2
    rules: list[StorageRuleItem] = Field(default_factory=list)
    status: str = "idle"
    cursor: int = 0
    queue_total: int = 0
    pending: int = 0
    progress_percent: float = 0.0
    stats: StorageStats
    last_run_at: str = ""
    last_error: str = ""
    started_at: str = ""
    updated_at: str = ""
    transfer_syntax_options: list[TransferSyntaxOption] = Field(default_factory=list)


class StorageActionResponse(BaseModel):
    status: str
    message: str = ""
    queue_total: int = 0
    pending: int = 0


class BackupTriggerResponse(BaseModel):
    requested: bool = True
    message: str = "Backup manual solicitado."


class AdGroupMappingItem(BaseModel):
    ad_group_cn: str = Field(min_length=1, max_length=128)
    lex_group: str = Field(min_length=1, max_length=32)


class AdConfigResponse(BaseModel):
    enabled: bool = False
    connection_url: str = ""
    use_ssl: bool = False
    bind_dn: str = ""
    bind_password_env: str = "AD_BIND_PASSWORD"
    users_dn: str = ""
    groups_dn: str = ""
    username_ldap_attribute: str = "sAMAccountName"
    import_users: bool = True
    group_mappings: list[AdGroupMappingItem] = Field(default_factory=list)
    full_sync_period_hours: int = 24
    changed_sync_period_hours: int = 1
    bind_password_configured: bool = False
    keycloak_realm: str = "lex-pacs"
    keycloak_configured: bool = False


class AdSyncMetaResponse(BaseModel):
    last_at: str = ""
    last_actor: str = ""
    users_imported: int = 0
    groups_mapped: int = 0
    memberships_applied: int = 0
    last_error: str = ""
    provider_configured: bool = False
    connection_ok: bool = False


class AdStatusResponse(BaseModel):
    config: AdConfigResponse
    sync: AdSyncMetaResponse
    lex_groups: list[str] = Field(default_factory=list)


class AdTestResponse(BaseModel):
    ok: bool = True
    message: str = ""


class AdSyncResponse(BaseModel):
    users_imported: int = 0
    groups_mapped: int = 0
    memberships_applied: int = 0
    message: str = ""


@router.get("/settings", response_model=PacsSettingsResponse)
async def read_settings() -> PacsSettingsResponse:
    return PacsSettingsResponse(**get_pacs_settings(equipment_count=len(get_equipment())))


@router.put("/settings", response_model=UpdateSettingsResponse)
async def write_settings(body: UpdateServerSettingsRequest) -> UpdateSettingsResponse:
    data = update_server_settings(
        dicom_aet=body.dicom_aet,
        name=body.name,
        dicom_check_called_aet=body.dicom_check_called_aet,
        dicom_check_modality_host=body.dicom_check_modality_host,
        dicom_restrict_inbound=body.dicom_restrict_inbound,
        ingest_transcoding=body.ingest_transcoding,
        worklists_enabled=body.worklists_enabled,
        worklists_filter_issuer_aet=body.worklists_filter_issuer_aet,
    )
    return UpdateSettingsResponse(**data)


@router.put("/settings/aet", response_model=UpdateSettingsResponse)
async def write_aet_only(body: UpdateAetRequest) -> UpdateSettingsResponse:
    current = get_pacs_settings()
    data = update_server_settings(
        dicom_aet=body.dicom_aet,
        name=current["name"],
        dicom_check_called_aet=current["dicom_check_called_aet"],
        dicom_check_modality_host=current["dicom_check_modality_host"],
        dicom_restrict_inbound=current["dicom_restrict_inbound"],
    )
    return UpdateSettingsResponse(
        dicom_aet=data["dicom_aet"],
        dicom_port=data["dicom_port"],
        name=data["name"],
        dicom_check_called_aet=data["dicom_check_called_aet"],
        dicom_check_modality_host=data["dicom_check_modality_host"],
        dicom_restrict_inbound=data["dicom_restrict_inbound"],
        registered_modality_count=data.get("registered_modality_count", 0),
        dicom_inbound_open_warning=data.get("dicom_inbound_open_warning", False),
        restarted=data["restarted"],
        message=data["message"],
    )


@router.get("/equipment", response_model=EquipmentListResponse)
async def read_equipment() -> EquipmentListResponse:
    return EquipmentListResponse(items=get_equipment())


@router.put("/equipment", response_model=EquipmentListResponse)
async def write_equipment(body: EquipmentListResponse) -> EquipmentListResponse:
    items = save_equipment([item.model_dump() for item in body.items])
    current = get_pacs_settings()
    update_server_settings(
        dicom_aet=current["dicom_aet"],
        name=current["name"],
        dicom_check_called_aet=current["dicom_check_called_aet"],
        dicom_check_modality_host=current["dicom_check_modality_host"],
        dicom_restrict_inbound=current["dicom_restrict_inbound"],
        equipment=items,
    )
    return EquipmentListResponse(items=items)


@router.get("/worklist-views", response_model=WorklistViewsResponse)
async def read_worklist_views() -> WorklistViewsResponse:
    return WorklistViewsResponse(views=get_worklist_views())


@router.put("/worklist-views", response_model=WorklistViewsResponse)
async def write_worklist_views(body: WorklistViewsResponse) -> WorklistViewsResponse:
    views = save_worklist_views([view.model_dump() for view in body.views])
    return WorklistViewsResponse(views=views)


@router.get("/mwl-sql", response_model=MwlSqlConfigResponse)
async def read_mwl_sql(
    _: ClinicalUser = Depends(require_clinical_user),
) -> MwlSqlConfigResponse:
    return MwlSqlConfigResponse(**get_mwl_sql_config())


@router.put("/mwl-sql", response_model=MwlSqlConfigResponse)
async def write_mwl_sql(
    body: MwlSqlConfigResponse,
    user: ClinicalUser = Depends(require_admin),
) -> MwlSqlConfigResponse:
    saved = save_mwl_sql_config(body.model_dump())
    log_event("mwl_sql_config", user.username, auth_method=user.auth_method)
    return MwlSqlConfigResponse(**saved)


@router.get("/mwl-sql/drivers")
async def read_mwl_drivers(
    _: ClinicalUser = Depends(require_clinical_user),
) -> dict:
    return {"drivers": list_drivers(), "mwl_fields": MWL_FIELDS}


@router.post("/mwl-sql/test-connection")
async def test_mwl_connection(
    user: ClinicalUser = Depends(require_admin),
) -> dict:
    result = test_connection(get_mwl_sql_config())
    log_event("mwl_sql_test", user.username, auth_method=user.auth_method)
    return result


@router.post("/mwl-sql/preview", response_model=MwlSqlPreviewResponse)
async def preview_mwl_sql(
    user: ClinicalUser = Depends(require_admin),
) -> MwlSqlPreviewResponse:
    cfg = get_mwl_sql_config()
    raw_rows: list[dict] = []
    columns: list[str] = []
    if str(cfg.get("mode")) == "custom":
        raw_rows = execute_select(cfg, str(cfg.get("custom_sql") or ""), limit=20)
        if raw_rows:
            columns = list(raw_rows[0].keys())
    mapped = fetch_mwl_source_rows(preview_limit=20)
    entries = [MwlEntry(**{
        "accession_number": row.get("accession_number", ""),
        "patient_id": row.get("patient_id", ""),
        "patient_name": row.get("patient_name", ""),
        "modality": row.get("modality", ""),
        "station_aet": row.get("station_aet", ""),
        "procedure_description": row.get("procedure_description", ""),
        "scheduled_date": str(row.get("scheduled_date", "")),
    }) for row in mapped]
    log_event("mwl_sql_preview", user.username, rows=len(entries), auth_method=user.auth_method)
    return MwlSqlPreviewResponse(columns=columns, raw_rows=raw_rows, mapped_entries=entries)


@router.get("/mwl/status", response_model=MwlStatusResponse)
async def read_mwl_status(
    _: ClinicalUser = Depends(require_clinical_user),
) -> MwlStatusResponse:
    plugin_enabled = await orthanc_mwl_plugin_enabled()
    entries = list_mwl_entries()
    return MwlStatusResponse(
        sql=MwlSqlConfigResponse(**get_mwl_sql_config()),
        sync=get_mwl_sync_meta(),
        plugin_enabled=plugin_enabled,
        entries_total=len(entries),
    )


@router.post("/mwl/sync", response_model=MwlSyncResponse)
async def trigger_mwl_sync(
    user: ClinicalUser = Depends(require_clinical_user),
) -> MwlSyncResponse:
    result = run_mwl_sync(actor=user.username)
    plugin_enabled = await orthanc_mwl_plugin_enabled()
    meta = get_mwl_sync_meta()
    log_event(
        "mwl_sync",
        user.username,
        synced=result["synced"],
        auth_method=user.auth_method,
    )
    return MwlSyncResponse(
        **result,
        plugin_enabled=plugin_enabled,
        last_at=meta.get("last_at", ""),
        last_actor=meta.get("last_actor", ""),
    )


@router.get("/mwl/entries", response_model=MwlEntriesResponse)
async def read_mwl_entries(
    station_aet: str = Query(default=""),
    _: ClinicalUser = Depends(require_clinical_user),
) -> MwlEntriesResponse:
    entries = [MwlEntry(**item) for item in list_mwl_entries(station_aet)]
    return MwlEntriesResponse(entries=entries)


@router.get("/backup/status", response_model=BackupStatusResponse)
async def read_backup_status(
    _: ClinicalUser = Depends(require_clinical_user),
) -> BackupStatusResponse:
    clear_backup_trigger()
    return BackupStatusResponse(**get_backup_status())


@router.post("/backup/trigger", response_model=BackupTriggerResponse)
async def trigger_backup_now(
    user: ClinicalUser = Depends(require_admin),
) -> BackupTriggerResponse:
    request_backup()
    log_event("backup_trigger", user.username, auth_method=user.auth_method)
    return BackupTriggerResponse()


@router.get("/storage/status", response_model=StorageStatusResponse)
async def read_storage_status(
    _: ClinicalUser = Depends(require_clinical_user),
) -> StorageStatusResponse:
    data = get_storage_status()
    return StorageStatusResponse(
        **{
            **data,
            "rules": [StorageRuleItem(**rule) for rule in data.get("rules") or []],
            "stats": StorageStats(**(data.get("stats") or {})),
            "transfer_syntax_options": [
                TransferSyntaxOption(**item) for item in data.get("transfer_syntax_options") or []
            ],
        }
    )


@router.put("/storage/config", response_model=StorageStatusResponse)
async def write_storage_config(
    body: StorageConfigRequest,
    user: ClinicalUser = Depends(require_admin),
) -> StorageStatusResponse:
    saved = save_storage_config(body.model_dump())
    log_event("storage_config", user.username, auth_method=user.auth_method)
    data = get_storage_status()
    return StorageStatusResponse(
        **{
            **data,
            "rules": [StorageRuleItem(**rule) for rule in saved.get("rules") or []],
            "stats": StorageStats(**(data.get("stats") or {})),
            "transfer_syntax_options": [
                TransferSyntaxOption(**item) for item in data.get("transfer_syntax_options") or []
            ],
        }
    )


@router.post("/storage/start", response_model=StorageActionResponse)
async def storage_start(
    user: ClinicalUser = Depends(require_admin),
) -> StorageActionResponse:
    result = start_storage_run()
    kick_storage_worker()
    log_event("storage_start", user.username, queue_total=result.get("queue_total", 0), auth_method=user.auth_method)
    return StorageActionResponse(
        status=str(result.get("status") or "running"),
        message="Compressão em lote iniciada.",
        queue_total=int(result.get("queue_total") or 0),
        pending=int(result.get("queue_total") or 0),
    )


@router.post("/storage/pause", response_model=StorageActionResponse)
async def storage_pause(
    user: ClinicalUser = Depends(require_admin),
) -> StorageActionResponse:
    result = pause_storage_run()
    log_event("storage_pause", user.username, auth_method=user.auth_method)
    return StorageActionResponse(status=str(result.get("status") or "paused"), message="Compressão pausada.")


@router.post("/storage/reset", response_model=StorageActionResponse)
async def storage_reset(
    user: ClinicalUser = Depends(require_admin),
) -> StorageActionResponse:
    result = reset_storage_run()
    log_event("storage_reset", user.username, auth_method=user.auth_method)
    return StorageActionResponse(status=str(result.get("status") or "idle"), message="Fila de compressão reiniciada.")


@router.get("/hl7/status", response_model=Hl7StatusResponse)
async def read_hl7_status(
    _: ClinicalUser = Depends(require_clinical_user),
) -> Hl7StatusResponse:
    return Hl7StatusResponse(
        config=Hl7ConfigResponse(**get_hl7_config()),
        stats=Hl7StatsResponse(**get_hl7_stats()),
    )


@router.put("/hl7/config", response_model=Hl7ConfigResponse)
async def write_hl7_config(
    body: Hl7ConfigResponse,
    user: ClinicalUser = Depends(require_admin),
) -> Hl7ConfigResponse:
    saved = save_hl7_config(body.model_dump())
    restart_hl7_mllp_server()
    log_event("hl7_config", user.username, auth_method=user.auth_method)
    return Hl7ConfigResponse(**saved)


@router.get("/mpps/status", response_model=MppsStatusResponse)
async def read_mpps_status(
    _: ClinicalUser = Depends(require_clinical_user),
) -> MppsStatusResponse:
    return MppsStatusResponse(
        config=MppsConfigResponse(**get_mpps_config()),
        stats=MppsStatsResponse(**get_mpps_stats()),
        server_running=mpps_server_running(),
    )


@router.put("/mpps/config", response_model=MppsConfigResponse)
async def write_mpps_config(
    body: MppsConfigResponse,
    user: ClinicalUser = Depends(require_admin),
) -> MppsConfigResponse:
    saved = save_mpps_config(body.model_dump())
    restart_mpps_server()
    log_event("mpps_config", user.username, auth_method=user.auth_method)
    return MppsConfigResponse(**saved)


@router.post("/mpps/simulate", response_model=MppsSimulateResponse)
async def simulate_mpps(
    body: MppsSimulateRequest,
    user: ClinicalUser = Depends(require_admin),
) -> MppsSimulateResponse:
    result = simulate_mpps_complete(body.accession_number, actor=user.username)
    log_event(
        "mpps_simulate",
        user.username,
        accession=body.accession_number,
        auth_method=user.auth_method,
    )
    return MppsSimulateResponse(
        applied=bool(result.get("applied")),
        accession=str(result.get("accession") or body.accession_number),
        mwl_deleted=bool(result.get("mwl_deleted")),
        worklist_file_removed=bool(result.get("worklist_file_removed")),
        reason=str(result.get("reason") or ""),
    )


@router.get("/qr/status", response_model=QrStatusResponse)
async def read_qr_status(
    _: ClinicalUser = Depends(require_clinical_user),
) -> QrStatusResponse:
    payload = build_qr_status_payload()
    return QrStatusResponse(
        dicom_aet=str(payload["dicom_aet"]),
        dicom_port=int(payload["dicom_port"]),
        orthanc=QrOrthancStatus(**payload["orthanc"]),
        config=QrConfigResponse(**payload["config"]),
        stats=QrStatsResponse(**payload["stats"]),
        consumers=[QrConsumerItem(**item) for item in payload.get("consumers") or []],
        consumer_count=int(payload.get("consumer_count") or 0),
        qr_ready=bool(payload.get("qr_ready")),
    )


@router.put("/qr/config", response_model=QrConfigResponse)
async def write_qr_config(
    body: QrConfigResponse,
    user: ClinicalUser = Depends(require_admin),
) -> QrConfigResponse:
    saved = save_qr_config(body.model_dump())
    build_qr_status_payload()
    log_event("qr_config", user.username, auth_method=user.auth_method)
    return QrConfigResponse(**saved)


@router.post("/qr/test-find", response_model=QrTestResponse)
async def test_qr_find(
    user: ClinicalUser = Depends(require_admin),
) -> QrTestResponse:
    try:
        result = test_c_find_study(actor=user.username)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    log_event(
        "qr_test_find",
        user.username,
        find_count=result.get("find_count", 0),
        success=result.get("success"),
        auth_method=user.auth_method,
    )
    return QrTestResponse(**result)


@router.get("/dicom-tls/status", response_model=DicomTlsStatusResponse)
async def read_dicom_tls_status(
    _: ClinicalUser = Depends(require_clinical_user),
) -> DicomTlsStatusResponse:
    payload = build_dicom_tls_status_payload()
    return DicomTlsStatusResponse(
        config=DicomTlsConfigResponse(**payload["config"]),
        stats=DicomTlsStatsResponse(**payload["stats"]),
        orthanc=DicomTlsOrthancStatus(**payload["orthanc"]),
        certificates=DicomTlsCertificatesStatus(**payload["certificates"]),
        dicom_aet=str(payload["dicom_aet"]),
        dicom_port=int(payload["dicom_port"]),
        tls_ready=bool(payload.get("tls_ready")),
    )


@router.put("/dicom-tls/config", response_model=DicomTlsConfigResponse)
async def write_dicom_tls_config(
    body: DicomTlsConfigResponse,
    user: ClinicalUser = Depends(require_admin),
) -> DicomTlsConfigResponse:
    saved = save_dicom_tls_config(body.model_dump())
    try:
        apply_dicom_tls_orthanc_settings()
    except HTTPException:
        if saved["enabled"]:
            save_dicom_tls_config({**saved, "enabled": False})
        raise
    log_event("dicom_tls_config", user.username, enabled=saved["enabled"], auth_method=user.auth_method)
    return DicomTlsConfigResponse(**saved)


@router.post("/dicom-tls/generate", response_model=DicomTlsStatusResponse)
async def generate_dicom_tls_certs(
    user: ClinicalUser = Depends(require_admin),
) -> DicomTlsStatusResponse:
    payload = generate_dev_certificates(actor=user.username)
    log_event("dicom_tls_generate", user.username, auth_method=user.auth_method)
    return DicomTlsStatusResponse(
        config=DicomTlsConfigResponse(**payload["config"]),
        stats=DicomTlsStatsResponse(**payload["stats"]),
        orthanc=DicomTlsOrthancStatus(**payload["orthanc"]),
        certificates=DicomTlsCertificatesStatus(**payload["certificates"]),
        dicom_aet=str(payload["dicom_aet"]),
        dicom_port=int(payload["dicom_port"]),
        tls_ready=bool(payload.get("tls_ready")),
    )


@router.post("/dicom-tls/test-echo", response_model=DicomTlsTestResponse)
async def test_dicom_tls(
    user: ClinicalUser = Depends(require_admin),
) -> DicomTlsTestResponse:
    result = test_dicom_tls_echo(actor=user.username)
    log_event(
        "dicom_tls_test_echo",
        user.username,
        success=result.get("success"),
        auth_method=user.auth_method,
    )
    return DicomTlsTestResponse(**result)


@router.get("/portal-ops", response_model=PortalOpsResponse)
async def read_portal_ops(
    _: ClinicalUser = Depends(require_clinical_user),
) -> PortalOpsResponse:
    return PortalOpsResponse(**get_portal_ops())


@router.put("/portal-ops", response_model=PortalOpsResponse)
async def write_portal_ops(
    body: PortalOpsResponse,
    user: ClinicalUser = Depends(require_admin),
) -> PortalOpsResponse:
    saved = save_portal_ops(body.model_dump())
    log_event("portal_ops", user.username, auth_method=user.auth_method)
    return PortalOpsResponse(**saved)


@router.get("/migration/status", response_model=MigrationStatusResponse)
async def read_migration_status(
    _: ClinicalUser = Depends(require_clinical_user),
) -> MigrationStatusResponse:
    return MigrationStatusResponse(**get_migration_status())


@router.put("/migration/config", response_model=MigrationConfigRequest)
async def write_migration_config(
    body: MigrationConfigRequest,
    user: ClinicalUser = Depends(require_admin),
) -> MigrationConfigRequest:
    saved = save_migration_settings(body.model_dump())
    log_event("migration_config", user.username, auth_method=user.auth_method)
    return MigrationConfigRequest(
        source=MigrationSource(**saved.get("source", {})),
        filters=MigrationFilters(**saved.get("filters", {})),
        batch_size=int(saved.get("batch_size") or 1),
        pause_seconds=int(saved.get("pause_seconds") or 2),
        skip_existing=bool(saved.get("skip_existing", True)),
    )


@router.post("/migration/test-echo")
async def migration_test_echo(
    user: ClinicalUser = Depends(require_admin),
) -> dict:
    result = test_migration_echo()
    log_event("migration_echo", user.username, auth_method=user.auth_method)
    return result


@router.post("/migration/discover", response_model=MigrationActionResponse)
async def migration_discover(
    user: ClinicalUser = Depends(require_admin),
) -> MigrationActionResponse:
    result = await asyncio.to_thread(run_migration_discovery)
    log_event(
        "migration_discover",
        user.username,
        discovered=result.get("discovered", 0),
        auth_method=user.auth_method,
    )
    return MigrationActionResponse(
        status="idle",
        message="Descoberta concluída.",
        discovered=int(result.get("discovered") or 0),
        queue_total=int(result.get("queue_total") or 0),
    )


@router.post("/migration/start", response_model=MigrationActionResponse)
async def migration_start(
    user: ClinicalUser = Depends(require_admin),
) -> MigrationActionResponse:
    result = start_migration()
    log_event("migration_start", user.username, auth_method=user.auth_method)
    return MigrationActionResponse(
        status=str(result.get("status") or "running"),
        message=str(result.get("message") or "Migração iniciada."),
        pending=int(result.get("pending") or 0),
    )


@router.post("/migration/pause", response_model=MigrationActionResponse)
async def migration_pause(
    user: ClinicalUser = Depends(require_admin),
) -> MigrationActionResponse:
    result = pause_migration()
    log_event("migration_pause", user.username, auth_method=user.auth_method)
    return MigrationActionResponse(
        status=str(result.get("status") or "paused"),
        message=str(result.get("message") or "Migração pausada."),
    )


@router.post("/migration/reset", response_model=MigrationActionResponse)
async def migration_reset(
    user: ClinicalUser = Depends(require_admin),
) -> MigrationActionResponse:
    result = reset_migration()
    log_event("migration_reset", user.username, auth_method=user.auth_method)
    return MigrationActionResponse(status=str(result.get("status") or "idle"), message="Migração resetada.")


@router.post("/hl7/test", response_model=Hl7TestResponse)
async def test_hl7_orm(
    body: Hl7TestRequest,
    user: ClinicalUser = Depends(require_admin),
) -> Hl7TestResponse:
    parsed_obj = parse_orm_message(body.message)
    parsed = {
        "message_id": parsed_obj.message_id,
        "message_type": parsed_obj.message_type,
        "order_control": parsed_obj.order_control,
        "accession_number": parsed_obj.accession_number,
        "patient_id": parsed_obj.patient_id,
        "patient_name": parsed_obj.patient_name,
        "modality": parsed_obj.modality,
        "station_aet": parsed_obj.station_aet,
        "procedure_description": parsed_obj.procedure_description,
        "scheduled_date": parsed_obj.scheduled_date.isoformat(),
        "is_cancel": parsed_obj.is_cancel,
    }
    result = None
    if body.apply:
        result = process_hl7_orm(body.message, actor=user.username)
        log_event(
            "hl7_orm",
            user.username,
            accession=parsed_obj.accession_number,
            control=parsed_obj.order_control,
            auth_method=user.auth_method,
        )
    return Hl7TestResponse(parsed=parsed, applied=body.apply, result=result)


@router.get("/ad/status", response_model=AdStatusResponse)
async def read_ad_status(
    _: ClinicalUser = Depends(require_clinical_user),
) -> AdStatusResponse:
    payload = ad_status_payload()
    return AdStatusResponse(
        config=AdConfigResponse(**payload["config"]),
        sync=AdSyncMetaResponse(**payload["sync"]),
        lex_groups=list(payload.get("lex_groups") or []),
    )


@router.put("/ad/config", response_model=AdConfigResponse)
async def write_ad_config(
    body: AdConfigResponse,
    user: ClinicalUser = Depends(require_admin),
) -> AdConfigResponse:
    saved = save_ad_config(body.model_dump())
    if saved.get("enabled"):
        try:
            await apply_ad_config_to_keycloak(saved)
            record_ad_sync_success(
                actor=user.username,
                users_imported=0,
                groups_mapped=len(saved.get("group_mappings") or []),
                memberships_applied=0,
            )
        except KeycloakAdminError as exc:
            record_ad_sync_error(actor=user.username, error=str(exc))
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    log_event("ad_config", user.username, auth_method=user.auth_method)
    return AdConfigResponse(**saved)


@router.post("/ad/test", response_model=AdTestResponse)
async def test_ad_ldap(
    user: ClinicalUser = Depends(require_admin),
) -> AdTestResponse:
    try:
        result = await test_ad_connection()
    except KeycloakAdminError as exc:
        record_ad_sync_error(actor=user.username, error=str(exc))
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    log_event("ad_test", user.username, auth_method=user.auth_method)
    return AdTestResponse(**result)


@router.post("/ad/sync", response_model=AdSyncResponse)
async def sync_ad_ldap(
    user: ClinicalUser = Depends(require_admin),
) -> AdSyncResponse:
    try:
        result = await sync_ad_users_and_groups(user.username)
    except KeycloakAdminError as exc:
        record_ad_sync_error(actor=user.username, error=str(exc))
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    record_ad_sync_success(
        actor=user.username,
        users_imported=int(result.get("users_imported") or 0),
        groups_mapped=int(result.get("groups_mapped") or 0),
        memberships_applied=int(result.get("memberships_applied") or 0),
    )
    log_event(
        "ad_sync",
        user.username,
        users=int(result.get("users_imported") or 0),
        groups=int(result.get("groups_mapped") or 0),
        auth_method=user.auth_method,
    )
    return AdSyncResponse(
        users_imported=int(result.get("users_imported") or 0),
        groups_mapped=int(result.get("groups_mapped") or 0),
        memberships_applied=int(result.get("memberships_applied") or 0),
        message="Usuários e grupos sincronizados com o Keycloak.",
    )


@router.get("/stats", response_model=PacsStatsResponse)
async def read_pacs_stats(
    _: ClinicalUser = Depends(require_clinical_user),
) -> PacsStatsResponse:
    return PacsStatsResponse(**await collect_pacs_stats())


@router.get("/audit", response_model=AuditListResponse)
async def read_audit_log(
    limit: int = Query(default=50, ge=1, le=500),
    event: str = Query(default=""),
    user: ClinicalUser = Depends(require_admin),
) -> AuditListResponse:
    events = list_events(limit=limit, event_type=event)
    log_event("audit_query", user.username, limit=limit, filter_event=event or None)
    return AuditListResponse(events=events)
