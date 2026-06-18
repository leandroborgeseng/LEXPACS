from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import HTTPException, status

from .config import settings

_AET_PATTERN = re.compile(r"^[A-Z0-9 _]{1,16}$")


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
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível ler a configuração do servidor de imagens.",
        ) from exc


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


def _sync_equipment_modalities(config: dict, equipment: list[dict]) -> None:
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
        }
    config["DicomModalities"] = modalities


def get_pacs_settings() -> dict:
    config = _read_config()
    pg = config.get("PostgreSQL", {})
    return {
        "dicom_aet": config.get("DicomAet", ""),
        "dicom_port": config.get("DicomPort", 4242),
        "name": config.get("Name", "LEX PACS"),
        "dicom_check_called_aet": bool(config.get("DicomCheckCalledAet")),
        "storage_directory": config.get("StorageDirectory", ""),
        "postgresql_index": bool(pg.get("EnableIndex")),
        "ingest_transcoding": config.get("IngestTranscoding", ""),
    }


def update_server_settings(
    *,
    dicom_aet: str,
    name: str,
    dicom_check_called_aet: bool,
    equipment: list[dict] | None = None,
) -> dict:
    normalized_aet = validate_aet(dicom_aet)
    institution = name.strip()[:64] or "LEX PACS"
    config = _read_config()
    previous_aet = config.get("DicomAet", "")
    previous_name = config.get("Name", "")
    previous_check = bool(config.get("DicomCheckCalledAet"))

    changed = (
        previous_aet != normalized_aet
        or previous_name != institution
        or previous_check != dicom_check_called_aet
    )

    config["DicomAet"] = normalized_aet
    config["Name"] = institution
    config["DicomCheckCalledAet"] = dicom_check_called_aet

    if equipment is not None:
        _sync_equipment_modalities(config, equipment)
        changed = True

    if changed:
        _write_config(config)

    return {
        "dicom_aet": normalized_aet,
        "dicom_port": config.get("DicomPort", 4242),
        "name": institution,
        "dicom_check_called_aet": dicom_check_called_aet,
        "restarted": changed,
        "message": (
            "Configurações salvas. O servidor DICOM será reiniciado em instantes."
            if changed
            else "Nenhuma alteração detectada."
        ),
    }


def update_dicom_aet(aet: str) -> dict:
    current = get_pacs_settings()
    result = update_server_settings(
        dicom_aet=aet,
        name=current["name"],
        dicom_check_called_aet=current["dicom_check_called_aet"],
    )
    return {
        "dicom_aet": result["dicom_aet"],
        "dicom_port": result["dicom_port"],
        "restarted": result["restarted"],
        "message": result["message"],
    }
