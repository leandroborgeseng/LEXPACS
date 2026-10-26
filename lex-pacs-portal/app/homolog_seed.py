"""Seed de HOMOLOGAÇÃO: N estudos DICOM SINTÉTICOS (nomes ZZTESTE inventados) no Orthanc da stack.

Uso (serviço `seed-homolog` do compose):  python -m app.homolog_seed
- HOMOLOG_SEED vazia/ausente  -> sai 0 sem fazer nada (produção não é afetada nem bloqueada).
- HOMOLOG_SEED=N              -> grava N estudos em ORTHANC_URL (padrão http://server:8042).
- Só aceita localhost, 127.0.0.1 e o host `server`; recusa qualquer outro (e o Orthanc de
  produção 172.21.31.198 explicitamente).
- Idempotente: se o Orthanc já tiver exames, não semeia.
- Termina só depois de todos os N estudos estarem gravados (confere /statistics).
- Credenciais só por variável de ambiente (ORTHANC_USERNAME / ORTHANC_PASSWORD). Sem PII em log.
"""
from __future__ import annotations

import io
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from urllib.parse import urlparse

import httpx

PRODUCAO = "172.21.31.198"
HOSTS_PERMITIDOS = {"localhost", "127.0.0.1", "server"}

SOBRENOMES = ["SANTOS", "OLIVEIRA", "SOUZA", "LIMA", "PEREIRA", "COSTA", "RODRIGUES", "ALMEIDA", "NASCIMENTO", "CARVALHO"]
NOMES = ["ANA", "JOSE", "MARIA", "PEDRO", "LUCAS", "JULIA", "PAULO", "CARLA", "RAFAEL", "BEATRIZ"]
NOMES_SEM_MARIA = [n for n in NOMES if n != "MARIA"]
MODS = ["CT", "MR", "CR", "DX", "US", "MG"]
ALVO = ("CONCEICAO^MARIA HELENA", "SINT-ALVO", "20180315")
ALVO_ACENTO = ("ÁVILA^JOÃO", "SINT-ALVO-ACENTO", "20190610")
ALVO_2023 = ("ZZTESTE^JOSÉ CONCEIÇÃO", "SINT-ZZ-2023", "20230505")
MARIA_HOMOLOG = 3500


class HostRecusado(ValueError):
    pass


def checar_host(url: str) -> str:
    """Devolve a URL sem barra final; levanta HostRecusado fora de localhost/127.0.0.1/server."""
    host = (urlparse(url).hostname or "").lower()
    if host == PRODUCAO or PRODUCAO in url:
        raise HostRecusado("Orthanc de produção (172.21.31.198) é proibido")
    if host not in HOSTS_PERMITIDOS:
        raise HostRecusado(f"host não permitido: {host or '(vazio)'}; só localhost, 127.0.0.1 ou server")
    return url.rstrip("/")


def dataset(i: int, name: str, pid: str, study_date: str, modality: str) -> bytes:
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = Dataset()
    ds.file_meta = meta
    ds.SpecificCharacterSet = "ISO_IR 192"
    ds.PatientName = name
    ds.PatientID = pid
    ds.PatientBirthDate = "19700101"
    ds.StudyInstanceUID = generate_uid()
    ds.SeriesInstanceUID = generate_uid()
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.Modality = modality
    ds.StudyDate = study_date
    ds.StudyTime = "101500"
    ds.AccessionNumber = f"ACC-SINT-{i:06d}"
    ds.StudyDescription = "ESTUDO SINTETICO"
    buf = io.BytesIO()
    ds.save_as(buf, enforce_file_format=True)
    return buf.getvalue()


def plano(n: int, maria: int = 0) -> list[tuple[int, str, str, str, str]]:
    """(i, nome, id, data, modalidade) de N estudos; os 3 alvos vão por último (fora dos 101).
    maria > 0: os primeiros `maria` estudos comuns são MARIA e o resto alterna ANA, JOSE, ..."""
    base = date(2026, 10, 26)
    alvo_idx = max(200, n * 3 // 4)
    total = max(n, alvo_idx + 3)
    alvos = {alvo_idx: (*ALVO, "CT"), alvo_idx + 1: (*ALVO_ACENTO, "MR"), alvo_idx + 2: (*ALVO_2023, "CT")}
    out, k = [], 0
    for i in range(total):
        if i in alvos:
            continue
        if maria:
            primeiro = "MARIA" if k < maria else NOMES_SEM_MARIA[k % len(NOMES_SEM_MARIA)]
        else:
            primeiro = NOMES[(i // 10) % 10]
        k += 1
        d = (base - timedelta(days=i % 3650)).strftime("%Y%m%d")
        out.append((i, f"ZZTESTE {SOBRENOMES[i % 10]}^{primeiro} {i:05d}", f"SINT-{i:06d}", d, MODS[i % len(MODS)]))
    out += [(i, *alvos[i]) for i in sorted(alvos)]
    return out


def contar_estudos(client: httpx.Client, url: str) -> int:
    r = client.get(f"{url}/statistics")
    r.raise_for_status()
    return int(r.json().get("CountStudies", 0) or 0)


def enviar(client: httpx.Client, url: str, itens, workers: int = 4) -> None:
    def send(it) -> None:
        body = dataset(*it)
        for attempt in range(8):
            r = client.post(f"{url}/instances", content=body)
            if r.status_code < 500:
                r.raise_for_status()
                return
            time.sleep(0.2 * (attempt + 1))
        raise RuntimeError(f"estudo {it[0]}: HTTP {r.status_code}")

    comuns, alvos = itens[:-3], itens[-3:]
    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(send, comuns))
    for it in alvos:
        send(it)


def run(env: dict | None = None, client_factory=httpx.Client) -> int:
    env = os.environ if env is None else env
    raw = (env.get("HOMOLOG_SEED") or "").strip()
    if not raw:
        print("seed-homolog: HOMOLOG_SEED vazia, nada a fazer")
        return 0
    try:
        n = int(raw)
    except ValueError:
        print("seed-homolog: HOMOLOG_SEED deve ser um número de estudos")
        return 2
    if n <= 0:
        print("seed-homolog: HOMOLOG_SEED <= 0, nada a fazer")
        return 0
    try:
        url = checar_host(env.get("ORTHANC_URL") or "http://server:8042")
    except HostRecusado as exc:
        print(f"seed-homolog: recusado: {exc}")
        return 3
    user, pwd = env.get("ORTHANC_USERNAME") or "", env.get("ORTHANC_PASSWORD") or ""
    auth = (user, pwd) if user else None
    with client_factory(auth=auth, timeout=60) as client:
        for _ in range(60):  # Orthanc pode demorar a aceitar HTTP depois do healthcheck
            try:
                atual = contar_estudos(client, url)
                break
            except httpx.HTTPError:
                time.sleep(5)
        else:
            print("seed-homolog: Orthanc não respondeu")
            return 4
        if atual > 0:
            print(f"seed-homolog: Orthanc já tem {atual} estudos, nada a fazer (idempotente)")
            return 0
        itens = plano(n, maria=min(MARIA_HOMOLOG, max(0, n - 200)))
        t0 = time.monotonic()
        enviar(client, url, itens)
        for _ in range(120):
            atual = contar_estudos(client, url)
            if atual >= len(itens):
                break
            time.sleep(1)
        else:
            print(f"seed-homolog: só {atual} de {len(itens)} estudos gravados")
            return 5
        print(f"seed-homolog: {atual} estudos sintéticos gravados em {time.monotonic() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(run())
