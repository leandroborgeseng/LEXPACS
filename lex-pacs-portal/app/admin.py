from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from .clinical_session import ClinicalUser
from .clinical_auth import require_admin, require_clinical_user
from .audit import list_events, log_event
from .mwl_scheduler import run_mwl_sync
from .mwl_sql import get_mwl_sql_config, get_mwl_sync_meta, save_mwl_sql_config
from .mwl_sync import list_mwl_entries, orthanc_mwl_plugin_enabled
from .lex_settings import (
    get_equipment,
    get_worklist_views,
    save_equipment,
    save_worklist_views,
)
from .backup_status import get_backup_status
from .pacs_config import get_pacs_settings, update_server_settings
from .pacs_stats import collect_pacs_stats

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
    dicom_check_called_aet: bool = False
    storage_directory: str = ""
    postgresql_index: bool = False
    ingest_transcoding: str = ""


class UpdateServerSettingsRequest(BaseModel):
    dicom_aet: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=1, max_length=64)
    dicom_check_called_aet: bool = False


class UpdateAetRequest(BaseModel):
    dicom_aet: str = Field(min_length=1, max_length=16)


class UpdateSettingsResponse(BaseModel):
    dicom_aet: str
    dicom_port: int
    name: str
    dicom_check_called_aet: bool
    restarted: bool
    message: str


class EquipmentListResponse(BaseModel):
    items: list[EquipmentItem]


class WorklistViewsResponse(BaseModel):
    views: list[WorklistViewItem]


class MwlSqlConfigResponse(BaseModel):
    enabled: bool = True
    host: str
    port: int
    database: str
    username: str
    password_env: str = "POSTGRES_PASSWORD"
    table: str = "lex_mwl_schedule"
    sync_interval_minutes: int = 5
    password_configured: bool = False


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


@router.get("/settings", response_model=PacsSettingsResponse)
async def read_settings() -> PacsSettingsResponse:
    return PacsSettingsResponse(**get_pacs_settings())


@router.put("/settings", response_model=UpdateSettingsResponse)
async def write_settings(body: UpdateServerSettingsRequest) -> UpdateSettingsResponse:
    data = update_server_settings(
        dicom_aet=body.dicom_aet,
        name=body.name,
        dicom_check_called_aet=body.dicom_check_called_aet,
    )
    return UpdateSettingsResponse(**data)


@router.put("/settings/aet", response_model=UpdateSettingsResponse)
async def write_aet_only(body: UpdateAetRequest) -> UpdateSettingsResponse:
    current = get_pacs_settings()
    data = update_server_settings(
        dicom_aet=body.dicom_aet,
        name=current["name"],
        dicom_check_called_aet=current["dicom_check_called_aet"],
    )
    return UpdateSettingsResponse(
        dicom_aet=data["dicom_aet"],
        dicom_port=data["dicom_port"],
        name=data["name"],
        dicom_check_called_aet=data["dicom_check_called_aet"],
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
    return BackupStatusResponse(**get_backup_status())


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
