"""Lista de estudos paginada no servidor (LP1–LP4, LP9 parcial, LP10) para o visualizador clínico.

POST /api/worklist/studies (gateway: /clinica-api/worklist/studies), com os filtros no CORPO da
requisição — nome, ID e nº de acesso não passam pela URL do gateway nem pelo access log.

Duas rotas de consulta ao Orthanc (somente leitura: QIDO GET, /tools/find e /tools/count-resources,
que não alteram nada):

1. Sem nome: QIDO com limit/offset (o Orthanc pagina) e total por /tools/count-resources
   (Orthanc >= 1.12.5; antes disso, pelo número de IDs do /tools/find). Se nada responder,
   o total fica desconhecido e só se sabe se há próxima.
2. Com nome: o Orthanc compara sem diferenciar maiúsculas, mas NÃO ignora acentos, e o "?" dele
   casa um byte, não uma letra (falha em "É", que tem 2 bytes em UTF-8). Por isso cada letra que
   pode ter acento (A E I O U C) vira "*" no padrão enviado ao Orthanc, que devolve um
   superconjunto; o portal filtra de novo com o nome normalizado (sem acento, maiúsculo), ordena
   por data (mais recente primeiro) e pagina. Limite: até MAX_CANDIDATOS candidatos; acima disso
   o total fica desconhecido e a tela pede para refinar (período, ID). As partes do nome podem
   vir em qualquer ordem ("jose conceicao" acha CONCEIÇÃO^JOSÉ).
"""
from __future__ import annotations

import re
import unicodedata

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .clinical_auth import require_clinical_user
from .config import settings

router = APIRouter(prefix="/api/worklist", tags=["worklist"], dependencies=[Depends(require_clinical_user)])

MIN_WILDCARD_CHARS = 3
MAX_CANDIDATOS = 50000  # cobre o PACS inteiro (~35 mil estudos)
INCLUDEFIELD = "00081030,00080060,00080090"
ACENTUAVEIS = set("AEIOUC")  # Ñ/Ý não ocorrem em nomes pt-BR
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


def strip_accents(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", value) if not unicodedata.combining(c))


def normalize_name(value: str | None) -> str:
    """Sem acento, maiúsculo, sem curingas digitados, separadores DICOM (^ ,) viram espaço."""
    text = strip_accents(str(value or "")).upper()
    text = re.sub(r"[*?\\]", "", text)
    text = re.sub(r"[\s^,=]+", " ", text)
    return text.strip()


def _significant(text: str) -> int:
    return len(re.sub(r"[^A-Z0-9]", "", text))


def uses_wildcard(name: str, disable_wildcard: bool = False) -> bool:
    return not disable_wildcard and _significant(name) >= MIN_WILDCARD_CHARS


def _relax(token: str) -> str:
    return re.sub(r"\*+", "*", "".join("*" if c in ACENTUAVEIS else c for c in token))


def orthanc_name_pattern(typed: str | None, disable_wildcard: bool = False) -> str | None:
    """Padrão (superconjunto) para o Orthanc: só a parte mais longa do nome digitado, com as
    letras acentuáveis trocadas por '*'. Usar uma parte só deixa a busca independente da ordem
    (o DICOM grava SOBRENOME^NOME, e o usuário costuma digitar "nome sobrenome")."""
    name = normalize_name(typed)
    if not name:
        return None
    if not uses_wildcard(name, disable_wildcard):
        return re.sub(r"\*+", "*", _relax(name.replace(" ", "^")))
    longest = max(name.split(" "), key=lambda t: (_significant(_relax(t)), len(t)))
    return re.sub(r"\*+", "*", f"*{_relax(longest)}*")


def name_matcher(typed: str | None, disable_wildcard: bool = False):
    """Confere o nome GRAVADO contra o digitado, ignorando acento e maiúsculas. Com curinga,
    cada parte digitada precisa aparecer no nome, em qualquer ordem."""
    name = normalize_name(typed)
    if not name:
        return lambda _stored: True
    if uses_wildcard(name, disable_wildcard):
        tokens = name.split(" ")
        return lambda stored: all(t in normalize_name(stored) for t in tokens)
    return lambda stored: normalize_name(stored) == name


def _exact(value: str | None) -> str | None:
    text = re.sub(r"[*?\\]", "", str(value or "")).strip()
    return text or None


def _date_range(q: WorklistQuery) -> str | None:
    for d in (q.startDate, q.endDate):
        if d and not _DATA.match(d):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Data inválida (AAAAMMDD).")
    if q.startDate and q.endDate:
        return f"{q.startDate}-{q.endDate}"
    if q.startDate:
        return f"{q.startDate}-"
    if q.endDate:
        return f"-{q.endDate}"
    return None


def _modalities(q: WorklistQuery) -> list[str]:
    mods = [m.strip().upper() for m in (q.modalitiesInStudy or []) if m and m.strip()]
    if any(not _MODALIDADE.match(m) for m in mods):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Modalidade inválida.")
    return mods


def _description(q: WorklistQuery) -> str | None:
    text = normalize_name(q.studyDescription)
    if not text:
        return None
    if uses_wildcard(text, q.disableWildcard):
        return f"*{text.replace(' ', '*')}*"
    return text


def common_filters(q: WorklistQuery) -> dict[str, str]:
    """Filtros comuns às duas rotas, na sintaxe DICOM aceita por QIDO e /tools/find."""
    out: dict[str, str] = {}
    if pid := _exact(q.patientId):
        out["PatientID"] = pid
    if acc := _exact(q.accessionNumber):
        out["AccessionNumber"] = acc
    if desc := _description(q):
        out["StudyDescription"] = desc
    if dr := _date_range(q):
        out["StudyDate"] = dr
    if mods := _modalities(q):
        out["ModalitiesInStudy"] = "\\".join(mods)
    return out


def _tag(study: dict, tag: str) -> str:
    v = (study.get(tag) or {}).get("Value") or [""]
    v = v[0]
    if isinstance(v, dict):
        return v.get("Alphabetic", "")
    return str(v)


def sort_recent_first(studies: list[dict]) -> list[dict]:
    return sorted(studies, key=lambda s: (_tag(s, "00080020"), _tag(s, "00080030")), reverse=True)


def _orthanc_error(exc: Exception) -> HTTPException:
    code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else 502
    return HTTPException(status.HTTP_502_BAD_GATEWAY, f"Não foi possível consultar o PACS (HTTP {code}).")


async def _qido(client: httpx.AsyncClient, params: dict) -> list[dict]:
    r = await client.get(f"{settings.orthanc_url.rstrip('/')}/dicom-web/studies", params=params)
    r.raise_for_status()
    return r.json() if r.status_code == 200 and r.text.strip() else []


async def _count(client: httpx.AsyncClient, query: dict) -> int | None:
    try:
        r = await client.post(
            f"{settings.orthanc_url.rstrip('/')}/tools/count-resources",
            json={"Level": "Study", "Query": query, "CaseSensitive": False},
        )
        if r.status_code == 200:
            return int(r.json().get("Count"))
        # Orthanc < 1.12.5 não tem count-resources: conta pelos IDs do /tools/find (sem Expand).
        r = await client.post(
            f"{settings.orthanc_url.rstrip('/')}/tools/find",
            json={"Level": "Study", "Query": query, "CaseSensitive": False, "Expand": False},
        )
        if r.status_code != 200:
            return None
        return len(r.json())
    except (httpx.HTTPError, ValueError, TypeError):
        return None


async def _page_without_name(client, q: WorklistQuery, filters: dict) -> dict:
    params = {**filters, "limit": q.limit + 1, "offset": q.offset, "includefield": INCLUDEFIELD}
    rows = await _qido(client, params)
    has_more = len(rows) > q.limit
    rows = rows[: q.limit]
    total = await _count(client, filters)
    if total is not None:
        has_more = q.offset + len(rows) < total
    return {"studies": sort_recent_first(rows), "total": total, "hasMore": has_more, "truncated": False}


async def _page_with_name(client, q: WorklistQuery, filters: dict) -> dict:
    pattern = orthanc_name_pattern(q.patientName, q.disableWildcard)
    matches = name_matcher(q.patientName, q.disableWildcard)
    r = await client.post(
        f"{settings.orthanc_url.rstrip('/')}/tools/find",
        json={
            "Level": "Study",
            "Query": {**filters, "PatientName": pattern},
            "CaseSensitive": False,
            "Expand": True,
            "Limit": MAX_CANDIDATOS + 1,
        },
    )
    r.raise_for_status()
    candidates = r.json()
    truncated = len(candidates) > MAX_CANDIDATOS
    hits = [
        c for c in candidates[:MAX_CANDIDATOS]
        if matches((c.get("PatientMainDicomTags") or {}).get("PatientName", ""))
    ]
    hits.sort(
        key=lambda c: ((c.get("MainDicomTags") or {}).get("StudyDate", ""),
                       (c.get("MainDicomTags") or {}).get("StudyTime", "")),
        reverse=True,
    )
    page = hits[q.offset: q.offset + q.limit]
    uids = [(c.get("MainDicomTags") or {}).get("StudyInstanceUID", "") for c in page]
    uids = [u for u in uids if u]
    rows: list[dict] = []
    if uids:
        rows = await _qido(client, {"StudyInstanceUID": ",".join(uids), "limit": len(uids),
                                    "includefield": INCLUDEFIELD})
        order = {u: i for i, u in enumerate(uids)}
        rows.sort(key=lambda s: order.get(_tag(s, "0020000D"), len(order)))
    return {
        "studies": rows,
        "total": None if truncated else len(hits),
        "hasMore": truncated or q.offset + len(page) < len(hits),
        "truncated": truncated,
    }


@router.post("/studies")
async def worklist_studies(q: WorklistQuery) -> dict:
    filters = common_filters(q)
    try:
        async with httpx.AsyncClient(timeout=60.0, auth=settings.orthanc_auth) as client:
            if normalize_name(q.patientName):
                result = await _page_with_name(client, q, filters)
            else:
                result = await _page_without_name(client, q, filters)
    except httpx.HTTPError as exc:
        raise _orthanc_error(exc) from exc
    return {**result, "offset": q.offset, "limit": q.limit}
