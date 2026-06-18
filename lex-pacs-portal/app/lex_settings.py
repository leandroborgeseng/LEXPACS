from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import HTTPException, status

from .config import settings

DEFAULT_WORKLIST_VIEWS = [
    {
        "id": "all",
        "label": "Todos",
        "modalities": [],
        "description": "",
        "station_aet": "",
    },
    {
        "id": "rx-sala-1",
        "label": "RX Sala 1",
        "modalities": ["CR", "DX"],
        "description": "sala 1",
        "station_aet": "RX_SALA1",
    },
    {
        "id": "rx-sala-2",
        "label": "RX Sala 2",
        "modalities": ["CR", "DX"],
        "description": "sala 2",
        "station_aet": "RX_SALA2",
    },
    {
        "id": "ct",
        "label": "CT",
        "modalities": ["CT"],
        "description": "",
        "station_aet": "",
    },
    {
        "id": "mr",
        "label": "MR",
        "modalities": ["MR"],
        "description": "",
        "station_aet": "",
    },
    {
        "id": "us",
        "label": "US",
        "modalities": ["US"],
        "description": "",
        "station_aet": "",
    },
]


def _settings_path() -> Path:
    return Path(settings.orthanc_config_path).parent / "lex-pacs-settings.json"


def _read_raw() -> dict:
    path = _settings_path()
    if not path.is_file():
        return {"equipment": [], "worklist_views": DEFAULT_WORKLIST_VIEWS}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível ler as configurações clínicas.",
        ) from exc
    if "worklist_views" not in data:
        data["worklist_views"] = DEFAULT_WORKLIST_VIEWS
    if "equipment" not in data:
        data["equipment"] = []
    return data


def _write_raw(data: dict) -> None:
    path = _settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível salvar as configurações clínicas.",
        ) from exc


def get_equipment() -> list[dict]:
    return _read_raw()["equipment"]


def save_equipment(items: list[dict]) -> list[dict]:
    normalized = []
    for item in items:
        aet = str(item.get("aet", "")).strip().upper()
        host = str(item.get("host", "")).strip()
        port = int(item.get("port", 104))
        description = str(item.get("description", "")).strip()[:64]
        modality = str(item.get("modality", "")).strip().upper()[:16]
        if not aet or not host:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cada equipamento precisa de AE Title e IP/host.",
            )
        if port < 1 or port > 65535:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Porta DICOM inválida.",
            )
        normalized.append(
            {
                "id": item.get("id") or str(uuid.uuid4()),
                "aet": aet,
                "host": host,
                "port": port,
                "description": description,
                "modality": modality,
            }
        )
    data = _read_raw()
    data["equipment"] = normalized
    _write_raw(data)
    return normalized


def get_worklist_views() -> list[dict]:
    return _read_raw()["worklist_views"]


def save_worklist_views(views: list[dict]) -> list[dict]:
    if not views:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Informe ao menos uma visão de worklist.",
        )
    normalized = []
    for view in views:
        view_id = str(view.get("id", "")).strip().lower().replace(" ", "-")
        label = str(view.get("label", "")).strip()
        if not view_id or not label:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cada visão precisa de id e nome.",
            )
        modalities = [str(m).strip().upper() for m in view.get("modalities", []) if str(m).strip()]
        normalized.append(
            {
                "id": view_id,
                "label": label,
                "modalities": modalities,
                "description": str(view.get("description", "")).strip(),
                "station_aet": str(view.get("station_aet", "")).strip().upper(),
            }
        )
    data = _read_raw()
    data["worklist_views"] = normalized
    _write_raw(data)
    return normalized
