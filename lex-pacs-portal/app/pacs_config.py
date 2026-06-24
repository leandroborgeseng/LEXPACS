from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import HTTPException, status

from .config import settings

_AET_PATTERN = re.compile(r"^[A-Z0-9 _]{1,16}$")

INGEST_TRANSCODING_OPTIONS = {
    "": "Sem transcodificação na ingestão",
    "1.2.840.10008.1.2.4.80": "JPEG-LS lossless",
    "1.2.840.10008.1.2.4.70": "JPEG lossless",
    "1.2.840.10008.1.2": "Little Endian explícito (sem compressão)",
}

JPEG_LS_DEFAULT = "1.2.840.10008.1.2.4.80"


def validate_ingest_transcoding(value: str) -> str:
    uid = value.strip()
    if uid and uid not in INGEST_TRANSCODING_OPTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transfer syntax de ingestão não suportado.",
        )
    return uid

# Padrão de mercado: C-STORE/MWL só de equipamentos cadastrados (E16).
_DICOM_SECURITY_DEFAULTS = {
    "DicomCheckCalledAet": True,
    "DicomCheckModalityHost": True,
    "DicomAlwaysAllowStore": False,
    "DicomAlwaysAllowEcho": False,
    "DicomAlwaysAllowFind": False,
    "DicomAlwaysAllowMove": False,
    "DicomAlwaysAllowGet": False,
}


def _config_path() -> Path:
    return Path(settings.orthanc_config_path)


def _read_config() -> dict:
    path = _config_path()
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Configuração do servidor de imagens indisponível.",
        )
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível ler a configuração do servidor de imagens.",
        ) from exc
    if _migrate_dicom_security(config):
        try:
            _write_config(config)
        except HTTPException:
            pass
    return config


def _migrate_dicom_security(config: dict) -> bool:
    changed = False
    for key, value in _DICOM_SECURITY_DEFAULTS.items():
        if key not in config:
            config[key] = value
            changed = True
    return changed


def _write_config(data: dict) -> None:
    path = _config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível salvar a configuração.",
        ) from exc


def validate_aet(value: str) -> str:
    normalized = value.strip().upper()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O AE Title não pode ser vazio.",
        )
    if len(normalized) > 16:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O AE Title deve ter no máximo 16 caracteres.",
        )
    if not _AET_PATTERN.match(normalized):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use apenas letras maiúsculas, números, espaço ou sublinhado.",
        )
    return normalized


def _apply_dicom_security_policy(config: dict, *, restrict_inbound: bool) -> None:
    if restrict_inbound:
        config["DicomAlwaysAllowStore"] = False
        config["DicomAlwaysAllowEcho"] = False
        config["DicomAlwaysAllowFind"] = False
        config["DicomAlwaysAllowMove"] = False
        config["DicomAlwaysAllowGet"] = False
    else:
        config["DicomAlwaysAllowStore"] = True
        config["DicomAlwaysAllowEcho"] = True
        config["DicomAlwaysAllowFind"] = True
        config["DicomAlwaysAllowMove"] = True
        config["DicomAlwaysAllowGet"] = True


def _sync_equipment_modalities(config: dict, equipment: list[dict]) -> None:
    modalities = _build_equipment_modalities_dict(equipment)
    try:
        from .migration_store import MIGRATION_MODALITY_KEY, get_migration_source_for_orthanc

        mig = get_migration_source_for_orthanc()
        if mig:
            modalities[MIGRATION_MODALITY_KEY] = mig
        else:
            modalities.pop(MIGRATION_MODALITY_KEY, None)
    except Exception:
        pass
    config["DicomModalities"] = modalities


def _build_equipment_modalities_dict(equipment: list[dict]) -> dict[str, dict]:
    modalities: dict[str, dict] = {}
    for item in equipment:
        key = re.sub(r"[^A-Za-z0-9_]", "_", item["aet"])[:32] or "DEVICE"
        suffix = 1
        base = key
        while key in modalities and modalities[key]["AET"] != item["aet"]:
            key = f"{base}_{suffix}"
            suffix += 1
        modalities[key] = {
            "AET": item["aet"],
            "Host": item["host"],
            "Port": item["port"],
            "AllowStore": True,
            "AllowEcho": True,
            "AllowFind": True,
            "AllowMove": True,
            "AllowGet": True,
        }
    return modalities


def _security_fields(config: dict, equipment_count: int = 0) -> dict:
    restrict = not bool(config.get("DicomAlwaysAllowStore", True))
    return {
        "dicom_check_called_aet": bool(config.get("DicomCheckCalledAet")),
        "dicom_check_modality_host": bool(config.get("DicomCheckModalityHost")),
        "dicom_restrict_inbound": restrict,
        "registered_modality_count": equipment_count,
        "dicom_inbound_open_warning": restrict and equipment_count == 0,
    }


def get_pacs_settings(*, equipment_count: int | None = None) -> dict:
    config = _read_config()
    pg = config.get("PostgreSQL", {})
    wl = config.get("Worklists", {})
    modalities = config.get("DicomModalities") or {}
    count = equipment_count if equipment_count is not None else len(modalities)
    ingest = str(config.get("IngestTranscoding", "") or "")
    if not ingest:
        ingest = JPEG_LS_DEFAULT
    return {
        "dicom_aet": config.get("DicomAet", ""),
        "dicom_port": config.get("DicomPort", 4242),
        "name": config.get("Name", "LEX PACS"),
        "storage_directory": config.get("StorageDirectory", ""),
        "postgresql_index": bool(pg.get("EnableIndex")),
        "ingest_transcoding": ingest,
        "ingest_transcoding_options": list(INGEST_TRANSCODING_OPTIONS.keys()),
        "worklists_enabled": bool(wl.get("Enable", True)),
        "worklists_filter_issuer_aet": bool(wl.get("FilterIssuerAet", False)),
        **_security_fields(config, count),
    }


def update_server_settings(
    *,
    dicom_aet: str,
    name: str,
    dicom_check_called_aet: bool,
    dicom_check_modality_host: bool | None = None,
    dicom_restrict_inbound: bool | None = None,
    ingest_transcoding: str | None = None,
    worklists_enabled: bool | None = None,
    worklists_filter_issuer_aet: bool | None = None,
    equipment: list[dict] | None = None,
) -> dict:
    normalized_aet = validate_aet(dicom_aet)
    institution = name.strip()[:64] or "LEX PACS"
    config = _read_config()
    previous_aet = config.get("DicomAet", "")
    previous_name = config.get("Name", "")
    previous_check = bool(config.get("DicomCheckCalledAet"))
    previous_host_check = bool(config.get("DicomCheckModalityHost"))
    previous_restrict = not bool(config.get("DicomAlwaysAllowStore", True))
    previous_ingest = str(config.get("IngestTranscoding", ""))
    wl = config.get("Worklists", {})
    previous_wl_enabled = bool(wl.get("Enable", True))
    previous_wl_filter = bool(wl.get("FilterIssuerAet", False))

    check_host = (
        dicom_check_modality_host
        if dicom_check_modality_host is not None
        else previous_host_check
    )
    restrict = (
        dicom_restrict_inbound if dicom_restrict_inbound is not None else previous_restrict
    )
    if ingest_transcoding is not None:
        ingest = validate_ingest_transcoding(ingest_transcoding)
    else:
        ingest = previous_ingest

    wl_enabled = worklists_enabled if worklists_enabled is not None else previous_wl_enabled
    wl_filter = (
        worklists_filter_issuer_aet
        if worklists_filter_issuer_aet is not None
        else previous_wl_filter
    )

    changed = (
        previous_aet != normalized_aet
        or previous_name != institution
        or previous_check != dicom_check_called_aet
        or previous_host_check != check_host
        or previous_restrict != restrict
        or (ingest_transcoding is not None and previous_ingest != ingest)
        or previous_wl_enabled != wl_enabled
        or previous_wl_filter != wl_filter
    )

    config["DicomAet"] = normalized_aet
    config["Name"] = institution
    config["DicomCheckCalledAet"] = dicom_check_called_aet
    config["DicomCheckModalityHost"] = check_host
    if ingest_transcoding is not None:
        if ingest:
            config["IngestTranscoding"] = ingest
        else:
            config.pop("IngestTranscoding", None)
    config["Worklists"] = {
        "Enable": wl_enabled,
        "FilterIssuerAet": wl_filter,
        "LimitAnswers": wl.get("LimitAnswers", 0),
        "Database": wl.get("Database", "/var/lib/orthanc/worklists"),
    }
    _apply_dicom_security_policy(config, restrict_inbound=restrict)

    if equipment is not None:
        _sync_equipment_modalities(config, equipment)
        changed = True

    if changed:
        _write_config(config)

    modalities = config.get("DicomModalities") or {}
    security = _security_fields(config, len(modalities))
    message = (
        "Configurações salvas. O servidor DICOM será reiniciado em instantes."
        if changed
        else "Nenhuma alteração detectada."
    )
    if security["dicom_inbound_open_warning"]:
        message += (
            " Atenção: restrição de entrada ativa sem equipamentos cadastrados — "
            "modalidades não conseguirão enviar exames até cadastrar AE + IP."
        )

    return {
        "dicom_aet": normalized_aet,
        "dicom_port": config.get("DicomPort", 4242),
        "name": institution,
        "ingest_transcoding": str(config.get("IngestTranscoding", "")),
        "worklists_enabled": wl_enabled,
        "worklists_filter_issuer_aet": wl_filter,
        "restarted": changed,
        "message": message,
        **security,
    }


def update_dicom_aet(aet: str) -> dict:
    current = get_pacs_settings()
    result = update_server_settings(
        dicom_aet=aet,
        name=current["name"],
        dicom_check_called_aet=current["dicom_check_called_aet"],
        dicom_check_modality_host=current["dicom_check_modality_host"],
        dicom_restrict_inbound=current["dicom_restrict_inbound"],
    )
    return {
        "dicom_aet": result["dicom_aet"],
        "dicom_port": result["dicom_port"],
        "restarted": result["restarted"],
        "message": result["message"],
    }
