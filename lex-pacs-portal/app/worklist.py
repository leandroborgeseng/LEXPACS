"""Lista de estudos paginada no servidor para o visualizador clínico (LP1–LP4, LP9, LP10, LP13).

POST /api/worklist/studies (gateway: /clinica-api/worklist/studies), com os filtros no CORPO da
requisição: nome, ID e nº de acesso não passam pela URL do gateway nem pelo access log.

Filtro, total e ordenação "mais recente primeiro" valem para o resultado TODO e saem do índice do
portal (app/worklist_index.py), sincronizado de forma incremental com o /changes do Orthanc. O
Orthanc só recebe QIDO GET com os UIDs da página. Busca por nome: sem acento, sem diferenciar
maiúsculas, cada parte digitada em qualquer ordem ("jose conceicao" acha CONCEIÇÃO^JOSÉ).
"""
from __future__ import annotations

import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import worklist_index
from .clinical_auth import require_clinical_user
from .config import settings
from .worklist_index import normalize_text

router = APIRouter(prefix="/api/worklist", tags=["worklist"], dependencies=[Depends(require_clinical_user)])

MIN_WILDCARD_CHARS = 3
INCLUDEFIELD = "00081030,00080060,00080090"
_DATA = re.compile(r"^\d{8}$")
_MODALIDADE = re.compile(r"^[A-Z0-9]{1,16}$")


class WorklistQuery(BaseModel):
    patientName: str | None = Field(default=None, max_length=128)
    patientId: str | None = Field(default=None, max_length=64)
    accessionNumber: str | None = Field(default=None, max_length=64)
    studyDescription: str | None = Field(default=None, max_length=128)
    modalitiesInStudy: list[str] | None = Field(default=None, max_length=20)
    startDate: str | None = None
    endDate: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0, le=1_000_000)
    disableWildcard: bool = False


def uses_wildcard(name: str, disable_wildcard: bool = False) -> bool:
    return not disable_wildcard and len(re.sub(r"[^a-z0-9]", "", name)) >= MIN_WILDCARD_CHARS


def _exact(value: str | None) -> str | None:
    text = re.sub(r"[*?\\]", "", str(value or "")).strip()
    return text or None


def _dates(q: WorklistQuery) -> tuple[str | None, str | None]:
    for d in (q.startDate, q.endDate):
        if d and not _DATA.match(d):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Data inválida (AAAAMMDD).")
    return q.startDate or None, q.endDate or None


def _modalities(q: WorklistQuery) -> list[str]:
    mods = [m.strip().upper() for m in (q.modalitiesInStudy or []) if m and m.strip()]
    if any(not _MODALIDADE.match(m) for m in mods):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Modalidade inválida.")
    return mods


def _tag(study: dict, tag: str) -> str:
    v = ((study.get(tag) or {}).get("Value") or [""])[0]
    return v.get("Alphabetic", "") if isinstance(v, dict) else str(v)


@router.post("/studies")
async def worklist_studies(q: WorklistQuery) -> dict:
    date_from, date_to = _dates(q)
    mods = _modalities(q)
    name = normalize_text(q.patientName)
    try:
        index = await worklist_index.sync_on_request()
        uids, total = worklist_index.search(
            name=name or None, wildcard=uses_wildcard(name, q.disableWildcard),
            patient_id=_exact(q.patientId), accession=_exact(q.accessionNumber),
            description=q.studyDescription, date_from=date_from, date_to=date_to,
            modalities=mods, limit=q.limit, offset=q.offset,
        )
        rows: list[dict] = []
        if uids:
            async with httpx.AsyncClient(timeout=60.0, auth=settings.orthanc_auth) as client:
                r = await client.get(
                    f"{settings.orthanc_url.rstrip('/')}/dicom-web/studies",
                    params={"StudyInstanceUID": ",".join(uids), "limit": len(uids), "includefield": INCLUDEFIELD},
                )
                r.raise_for_status()
                rows = r.json() if r.status_code == 200 and r.text.strip() else []
            order = {u: i for i, u in enumerate(uids)}
            rows.sort(key=lambda s: order.get(_tag(s, "0020000D"), len(order)))
    except httpx.HTTPError as exc:
        code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else 502
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            f"Não foi possível consultar o PACS (HTTP {code}).") from exc
    return {
        "studies": rows,
        "total": total,
        "hasMore": q.offset + len(uids) < total,
        "truncated": False,
        "sortScope": "global",
        # Enquanto a carga inicial não termina, o resultado é parcial (só o que já foi indexado).
        "index": {"status": index["status"], "indexed": index.get("indexed") or 0, "total": index.get("total")},
        "partial": index["status"] != "ready",
        "offset": q.offset,
        "limit": q.limit,
    }
