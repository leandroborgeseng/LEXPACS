"""Índice de busca da lista de exames (LP13, LP10 global, busca sem acento sem curinga relaxado).

Tabela SQLite própria do portal com metadados de ESTUDO (sem pixel, sem nome original):
UID, ID Orthanc, data/hora, nome normalizado (sem acento, minúsculo), modalidades, ID do
paciente, nº de acesso e descrição normalizada. Leitura do Orthanc só por GET:
- carga inicial: QIDO /dicom-web/studies paginado (limit/offset);
- incremental: GET /changes?since=<checkpoint> (NewStudy/StableStudy => QIDO pelo UID;
  Deleted de estudo => remove), checkpoint salvo na tabela `worklist_meta`.
Migração só aditiva (CREATE TABLE/INDEX IF NOT EXISTS). Nada é escrito no Orthanc e nenhum
nome/ID vai para log.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import threading
import time
import re
import sqlite3
import unicodedata
from pathlib import Path

import httpx

from .config import settings

BATCH = 1000
CHANGES_LIMIT = 1000
SCHEMA = """
CREATE TABLE IF NOT EXISTS worklist_study (
    study_uid TEXT PRIMARY KEY,
    orthanc_id TEXT NOT NULL,
    study_date TEXT NOT NULL DEFAULT '',
    study_time TEXT NOT NULL DEFAULT '',
    name_norm TEXT NOT NULL DEFAULT '',
    modalities TEXT NOT NULL DEFAULT '',
    patient_id TEXT NOT NULL DEFAULT '',
    accession TEXT NOT NULL DEFAULT '',
    description_norm TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_worklist_date ON worklist_study (study_date DESC, study_time DESC, study_uid DESC);
CREATE INDEX IF NOT EXISTS ix_worklist_orthanc ON worklist_study (orthanc_id);
CREATE INDEX IF NOT EXISTS ix_worklist_pid ON worklist_study (patient_id);
CREATE INDEX IF NOT EXISTS ix_worklist_acc ON worklist_study (accession);
CREATE TABLE IF NOT EXISTS worklist_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def strip_accents(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", value) if not unicodedata.combining(c))


def normalize_text(value: str | None) -> str:
    """Sem acento, minúsculo, sem curingas, separadores DICOM (^ , =) viram espaço."""
    text = strip_accents(str(value or "")).lower()
    text = re.sub(r"[*?\\%_]", "", text)
    text = re.sub(r"[\s^,=]+", " ", text)
    return text.strip()


def orthanc_study_id(patient_id: str, study_uid: str) -> str:
    """ID Orthanc do estudo: SHA-1 de "PatientID|StudyInstanceUID" em 5 grupos de 8."""
    h = hashlib.sha1(f"{patient_id}|{study_uid}".encode()).hexdigest()
    return "-".join(h[i:i + 8] for i in range(0, 40, 8))


def index_path() -> Path:
    if settings.worklist_index_path:
        return Path(settings.worklist_index_path)
    return Path(settings.local_users_db_path).with_name("worklist_index.db")


def shadow_path() -> Path:
    """Base-sombra da reconstrução: mesma pasta (mesmo volume) para o os.replace ser atômico."""
    p = index_path()
    return p.with_name(p.name + ".shadow")


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Abre o índice. O arquivo nasce 0600 (só o usuário do portal) e fica no volume do portal,
    que o gateway nginx não monta: não há como servi-lo por HTTP."""
    path = Path(path) if path else index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        os.close(os.open(path, os.O_CREAT | os.O_WRONLY, 0o600))
    os.chmod(path, 0o600)
    conn = sqlite3.connect(path, timeout=30)
    conn.executescript(SCHEMA)
    return conn


# Estado da indexação (sem PII): status idle|indexing|rebuilding|ready|incomplete|error, indexados e
# total do Orthanc. rebuilding = já existe índice completo em uso (a busca funciona normalmente) e
# uma reconstrução/conferência roda em segundo plano; indexing = primeira carga (resultado parcial).
_state_lock = threading.Lock()
_state = {"status": "idle", "indexed": 0, "total": None}


def retry_in_seconds() -> int:
    """Quanto falta para poder tentar a carga de novo (0 = já pode). Só vale em erro."""
    with _state_lock:
        if _state["status"] not in ("error", "incomplete") or _last_attempt is None:
            return 0
        left = settings.worklist_index_retry_seconds - (time.monotonic() - _last_attempt)
    return max(0, int(left + 0.999))


def next_auto_retry_in_seconds() -> int | None:
    """Segundos até a próxima tentativa automática (None = nenhuma agendada)."""
    with _state_lock:
        if _next_retry_at is None:
            return None
        left = _next_retry_at - time.monotonic()
    return max(0, int(left + 0.999))


def state() -> dict:
    with _state_lock:
        st = dict(_state)
    st["retryInSeconds"] = retry_in_seconds() if st["status"] in ("error", "incomplete") else 0
    st["nextAutoRetryInSeconds"] = next_auto_retry_in_seconds() if st["status"] in ("error", "incomplete") else None
    return st


def _set_state(**kw) -> None:
    with _state_lock:
        _state.update(kw)


def is_ready() -> bool:
    conn = connect()
    try:
        return _meta_get(conn, "full_load_done") == "1"
    finally:
        conn.close()


def _tag(study: dict, tag: str) -> str:
    v = ((study.get(tag) or {}).get("Value") or [""])[0]
    if isinstance(v, dict):
        return v.get("Alphabetic", "") or ""
    return str(v or "")


def _tags(study: dict, tag: str) -> list[str]:
    return [str(v) for v in ((study.get(tag) or {}).get("Value") or []) if v]


def row_from_qido(study: dict) -> tuple | None:
    uid = _tag(study, "0020000D")
    if not uid:
        return None
    pid = _tag(study, "00100020")
    mods = _tags(study, "00080061")
    return (
        uid,
        orthanc_study_id(pid, uid),
        _tag(study, "00080020"),
        _tag(study, "00080030"),
        normalize_text(_tag(study, "00100010")),
        ("\\" + "\\".join(m.upper() for m in mods) + "\\") if mods else "",
        pid,
        _tag(study, "00080050"),
        normalize_text(_tag(study, "00081030")),
    )


UPSERT = """INSERT INTO worklist_study VALUES (?,?,?,?,?,?,?,?,?)
ON CONFLICT(study_uid) DO UPDATE SET orthanc_id=excluded.orthanc_id, study_date=excluded.study_date,
study_time=excluded.study_time, name_norm=excluded.name_norm, modalities=excluded.modalities,
patient_id=excluded.patient_id, accession=excluded.accession, description_norm=excluded.description_norm"""
QIDO_FIELDS = "00080030,00080050,00081030,00080061"


def _base() -> str:
    return settings.orthanc_url.rstrip("/")


def _meta_get(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM worklist_meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def _meta_set(conn, key: str, value) -> None:
    conn.execute("INSERT INTO worklist_meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, str(value)))


async def _qido(client: httpx.AsyncClient, params: dict) -> list[dict]:
    r = await client.get(f"{_base()}/dicom-web/studies", params=params)
    r.raise_for_status()
    return r.json() if r.status_code == 200 and r.text.strip() else []


async def full_load(client: httpx.AsyncClient, path: Path | None = None) -> int:
    """Carga inicial (só GET). O checkpoint é o /changes de ANTES da carga, para não perder nada.
    path: base de destino (padrão: o índice em uso; na reconstrução, a base-sombra)."""
    r = await client.get(f"{_base()}/changes", params={"last": ""})
    r.raise_for_status()
    checkpoint = int(r.json().get("Last", 0))
    t0 = time.perf_counter()
    total = None
    try:
        st = await client.get(f"{_base()}/statistics")
        if st.status_code == 200:
            total = int(st.json().get("CountStudies"))
    except (httpx.HTTPError, ValueError, TypeError):
        total = None
    # Carga na base-sombra (path informado): a busca segue no índice atual => "rebuilding".
    _set_state(status="rebuilding" if path is not None and _count_index() > 0 else "indexing", indexed=0, total=total)
    conn = connect(path)
    try:
        # O Orthanc pode cortar cada consulta em LimitFindResults (ex.: 100) mesmo pedindo BATCH:
        # avança o offset pelo que veio de fato e só para com lote vazio (ou sem nada novo, caso
        # o servidor ignore o offset).
        offset = 0
        seen: set[str] = set()
        while True:
            rows = await _qido(client, {"limit": BATCH, "offset": offset, "includefield": QIDO_FIELDS})
            if not rows:
                break
            vals = [v for v in (row_from_qido(s) for s in rows) if v]
            novos = {v[0] for v in vals} - seen
            conn.executemany(UPSERT, vals)
            conn.commit()  # cada lote já fica visível para busca parcial
            seen |= novos
            _set_state(indexed=len(seen))
            if not novos:
                break
            offset += len(rows)
        n = conn.execute("SELECT COUNT(*) FROM worklist_study").fetchone()[0]
        if total is not None and n < total:
            # Incompleto: NÃO grava full_load_done (o próximo startup recarrega) e não finge "ready".
            _set_state(status="incomplete", indexed=n, total=total)
            print(f"worklist_index: carga incompleta, {n} de {total} estudos")
            return n
        _meta_set(conn, "changes_seq", checkpoint)
        _meta_set(conn, "full_load_done", 1)
        conn.commit()
        _set_state(status="ready", indexed=n, total=total if total is not None else n)
        print(f"worklist_index: carga inicial de {n} estudos em {time.perf_counter() - t0:.1f} s")
        return n
    finally:
        conn.close()


async def incremental(client: httpx.AsyncClient) -> int:
    conn = connect()
    try:
        since = int(_meta_get(conn, "changes_seq") or 0)
        applied = 0
        while True:
            r = await client.get(f"{_base()}/changes", params={"since": since, "limit": CHANGES_LIMIT})
            r.raise_for_status()
            data = r.json()
            for ch in data.get("Changes", []):
                if ch.get("ResourceType") != "Study":
                    continue
                kind, oid = ch.get("ChangeType"), ch.get("ID", "")
                if kind == "Deleted":
                    conn.execute("DELETE FROM worklist_study WHERE orthanc_id=?", (oid,))
                    applied += 1
                elif kind in ("NewStudy", "StableStudy", "UpdatedAttachment", "UpdatedMetadata"):
                    s = await client.get(f"{_base()}/studies/{oid}")
                    if s.status_code == 404:
                        conn.execute("DELETE FROM worklist_study WHERE orthanc_id=?", (oid,))
                        continue
                    s.raise_for_status()
                    uid = (s.json().get("MainDicomTags") or {}).get("StudyInstanceUID", "")
                    if uid:
                        for q in await _qido(client, {"StudyInstanceUID": uid, "includefield": QIDO_FIELDS}):
                            if v := row_from_qido(q):
                                conn.execute(UPSERT, v)
                                applied += 1
            since = int(data.get("Last", since))
            _meta_set(conn, "changes_seq", since)
            conn.commit()
            if data.get("Done", True):
                break
        return applied
    finally:
        conn.close()


# Um único lock (entre threads e requisições): nunca há duas sincronizações ao mesmo tempo.
_sync_lock = threading.Lock()
_bg_thread: threading.Thread | None = None


def _count_index() -> int:
    conn = connect()
    try:
        return conn.execute("SELECT COUNT(*) FROM worklist_study").fetchone()[0]
    finally:
        conn.close()


async def _orthanc_count(client: httpx.AsyncClient) -> int | None:
    try:
        r = await client.get(f"{_base()}/statistics")
        r.raise_for_status()
        return int(r.json().get("CountStudies", 0) or 0)
    except (httpx.HTTPError, ValueError, TypeError):
        return None


async def _run_sync(full: bool, check_complete: bool = False, rebuild: bool = False) -> None:
    """check_complete (startup): depois do incremental, se o índice tiver menos estudos que o
    Orthanc (ex.: carga antiga cortada pelo LimitFindResults e marcada como pronta), reconstrói
    sozinho. rebuild: reconstrução explícita. Toda reconstrução com índice já preenchido carrega
    numa base-sombra e troca atomicamente no fim: a busca continua com os dados antigos."""
    async with httpx.AsyncClient(timeout=120.0, auth=settings.orthanc_auth) as client:
        if rebuild:
            await _shadow_rebuild(client)
            return
        if full:
            if _count_index() > 0:
                await _shadow_rebuild(client)
                return
            await full_load(client)  # índice vazio: carrega direto (resultado parcial visível)
            if state()["status"] == "incomplete":
                return
        await incremental(client)
        if check_complete and not full:
            total = await _orthanc_count(client)
            # Diferença em qualquer sentido: a menos (carga cortada) ou a mais (estudo apagado no
            # Orthanc sem evento no /changes, ex.: /changes podado) => reconstrói em sombra.
            if total is not None and _count_index() != total:
                print(f"worklist_index: índice com {_count_index()} de {total} estudos, reconstruindo")
                await _shadow_rebuild(client)


def _drop_shadow() -> None:
    for suffix in ("", "-journal", "-wal", "-shm"):
        p = Path(str(shadow_path()) + suffix)
        if p.exists():
            p.unlink()


async def _shadow_rebuild(client: httpx.AsyncClient) -> None:
    """Carrega o acervo inteiro na base-sombra e só então troca (os.replace, atômico no mesmo
    volume). Conexões abertas terminam a leitura no arquivo antigo; as novas já veem o novo.
    Carga incompleta: troca só se a sombra tiver MAIS estudos que o índice atual (sem marcar
    full_load_done); senão descarta a sombra e a busca segue com o índice antigo."""
    _drop_shadow()
    shadow = shadow_path()
    try:
        await full_load(client, shadow)
        complete = state()["status"] != "incomplete"
        conn = connect(shadow)
        try:
            n_shadow = conn.execute("SELECT COUNT(*) FROM worklist_study").fetchone()[0]
        finally:
            conn.close()
        if complete or n_shadow > _count_index():
            os.chmod(shadow, 0o600)
            os.replace(shadow, index_path())
        if complete:
            await incremental(client)
    finally:
        _drop_shadow()


def _background_full(rebuild: bool = False) -> None:
    with _sync_lock:
        try:
            if rebuild:
                asyncio.run(_run_sync(full=True, rebuild=True))
            elif is_ready():
                asyncio.run(_run_sync(full=False, check_complete=True))
            else:
                asyncio.run(_run_sync(full=True))
            if state()["status"] != "incomplete":
                n = _count_index()
                _set_state(status="ready", indexed=n, total=n)
        except Exception as exc:  # sem PII: só o tipo
            _set_state(status="error")
            print(f"worklist_index: sincronização falhou ({type(exc).__name__})")
    _after_attempt()


_last_attempt: float | None = None
_next_retry_at: float | None = None
_retry_attempts = 0
_retry_timer: threading.Timer | None = None


def retry_delay(attempts: int) -> float:
    """Backoff exponencial: intervalo base, 2x, 4x… até WORKLIST_INDEX_RETRY_MAX_SECONDS."""
    base = max(1, settings.worklist_index_retry_seconds)
    return float(min(base * (2 ** max(0, attempts)), max(base, settings.worklist_index_retry_max_seconds)))


def _after_attempt() -> None:
    """Fim de uma tentativa (thread em segundo plano). incomplete/error => agenda a próxima num
    timer com backoff; NENHUMA busca dispara carga. ready => zera o backoff."""
    global _retry_attempts, _next_retry_at, _retry_timer
    with _state_lock:
        st = _state["status"]
        if st == "ready":
            _retry_attempts = 0
            _next_retry_at = None
            return
        if st not in ("error", "incomplete") or not settings.worklist_index_auto_retry:
            return
        delay = retry_delay(_retry_attempts)
        _retry_attempts += 1
        _next_retry_at = time.monotonic() + delay
        if _retry_timer is not None:
            _retry_timer.cancel()
        _retry_timer = threading.Timer(delay, _auto_retry)
        _retry_timer.daemon = True
        _retry_timer.start()
    print(f"worklist_index: nova tentativa automática em {int(delay)} s (tentativa {_retry_attempts})")


def _auto_retry() -> None:
    start_background(_auto=True)


def cancel_auto_retry() -> None:
    global _retry_timer, _next_retry_at, _retry_attempts
    with _state_lock:
        if _retry_timer is not None:
            _retry_timer.cancel()
        _retry_timer = None
        _next_retry_at = None
        _retry_attempts = 0


def start_background(rebuild: bool = False, _auto: bool = False) -> threading.Thread | None:
    """Carga inicial (ou reconstrução) numa thread em segundo plano; idempotente. Depois de uma
    falha, nova tentativa manual só após WORKLIST_INDEX_RETRY_SECONDS (padrão 60 s); as
    automáticas vêm do timer com backoff. A reconstrução explícita (rebuild=True) não espera.
    Devolve None quando não inicia."""
    global _bg_thread, _last_attempt
    ready = is_ready()  # fora do lock de estado (abre o SQLite)
    with _state_lock:
        if _bg_thread and _bg_thread.is_alive():
            return _bg_thread
        now = time.monotonic()
        if (not rebuild and not _auto and _state["status"] in ("error", "incomplete")
                and _last_attempt is not None
                and now - _last_attempt < settings.worklist_index_retry_seconds):
            return None
        _last_attempt = now
        _state.update(status="rebuilding" if ready else "indexing")
        _bg_thread = threading.Thread(target=_background_full, args=(rebuild,), name="worklist-index",
                                      daemon=True)
        _bg_thread.start()
        return _bg_thread


async def sync_on_request() -> dict:
    """Na busca: nunca espera nem dispara carga completa (a nova tentativa de incomplete/error é
    do timer em segundo plano). Pronto => incremental, só se o lock estiver livre."""
    if not is_ready():
        if _state["status"] == "idle" and _bg_thread is None:
            start_background()  # só se nada rodou ainda neste processo (ex.: autostart desligado)
        return state()
    if _sync_lock.acquire(blocking=False):
        try:
            await _run_sync(full=False)
        finally:
            _sync_lock.release()
    if state()["status"] == "ready":
        n = _count_index()
        _set_state(indexed=n, total=n)
    return state()


async def _sync_now_for_tests() -> None:
    """SÓ PARA TESTES: sincroniza já, sob o mesmo lock. Nenhuma rota chama isto (há teste)."""
    with _sync_lock:
        await _run_sync(full=not is_ready())
        _set_state(status="ready")


def search(*, name: str | None, wildcard: bool, patient_id: str | None, accession: str | None,
           description: str | None, date_from: str | None, date_to: str | None,
           modalities: list[str], limit: int, offset: int) -> tuple[list[str], int]:
    """Filtra e ordena (mais recente primeiro) no índice inteiro; devolve UIDs da página e total."""
    where, args = [], []
    tokens = normalize_text(name).split()
    if tokens:
        if wildcard:
            for t in tokens:  # todas as partes, em qualquer ordem
                where.append("instr(name_norm, ?) > 0")
                args.append(t)
        else:
            where.append("name_norm = ?")
            args.append(" ".join(tokens))
    if patient_id:
        where.append("patient_id = ?")
        args.append(patient_id)
    if accession:
        where.append("accession = ?")
        args.append(accession)
    for t in normalize_text(description).split():
        where.append("instr(description_norm, ?) > 0")
        args.append(t)
    if date_from:
        where.append("study_date >= ?")
        args.append(date_from)
    if date_to:
        where.append("study_date <= ?")
        args.append(date_to)
    if modalities:
        where.append("(" + " OR ".join("instr(modalities, ?) > 0" for _ in modalities) + ")")
        args += [f"\\{m}\\" for m in modalities]
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    conn = connect()
    try:
        total = conn.execute(f"SELECT COUNT(*) FROM worklist_study{clause}", args).fetchone()[0]
        uids = [r[0] for r in conn.execute(
            f"SELECT study_uid FROM worklist_study{clause} "
            "ORDER BY study_date DESC, study_time DESC, study_uid DESC LIMIT ? OFFSET ?",
            [*args, limit, offset])]
        return uids, total
    finally:
        conn.close()
