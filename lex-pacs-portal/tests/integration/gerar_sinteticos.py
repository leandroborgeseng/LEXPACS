"""Gera N estudos DICOM SINTÉTICOS (nomes e IDs inventados) e envia a um Orthanc descartável."""
import argparse
import io
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import httpx
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

SOBRENOMES = ["SANTOS", "OLIVEIRA", "SOUZA", "LIMA", "PEREIRA", "COSTA", "RODRIGUES", "ALMEIDA", "NASCIMENTO", "CARVALHO"]
NOMES = ["ANA", "JOSE", "MARIA", "PEDRO", "LUCAS", "JULIA", "PAULO", "CARLA", "RAFAEL", "BEATRIZ"]
MODS = ["CT", "MR", "CR", "DX", "US", "MG"]
# Alvo bem depois dos 101 primeiros; nome gravado SEM acento (padrão RIS) e outro COM acento.
ALVO = ("CONCEICAO^MARIA HELENA", "SINT-ALVO", "20180315")
ALVO_ACENTO = ("ÁVILA^JOÃO", "SINT-ALVO-ACENTO", "20190610")
# Paginação/LP9: nome com acento, de 2023 (fora dos 7 dias e dos 101), marcador ZZTESTE para grep nos logs.
ALVO_2023 = ("ZZTESTE^JOSÉ CONCEIÇÃO", "SINT-ZZ-2023", "20230505")


def dataset(i: int, name: str, pid: str, study_date: str, modality: str) -> bytes:
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--n", type=int, default=1500)
    a = ap.parse_args()
    assert "127.0.0.1" in a.url or "localhost" in a.url, "só Orthanc local descartável"
    base = date(2026, 10, 26)
    alvo_idx = max(200, a.n * 3 // 4)  # sempre bem depois dos 101 primeiros

    def item(i: int):
        if i == alvo_idx:
            return dataset(i, *ALVO, "CT")
        if i == alvo_idx + 1:
            return dataset(i, *ALVO_ACENTO, "MR")
        if i == alvo_idx + 2:
            return dataset(i, *ALVO_2023, "CT")
        name = f"ZZTESTE {SOBRENOMES[i % 10]}^{NOMES[(i // 10) % 10]} {i:05d}"
        d = (base - timedelta(days=i % 3650)).strftime("%Y%m%d")
        return dataset(i, name, f"SINT-{i:06d}", d, MODS[i % len(MODS)])

    with httpx.Client(auth=(a.user, a.password), timeout=60) as client:
        def send(i: int) -> None:
            body = item(i)
            for attempt in range(5):
                r = client.post(f"{a.url}/instances", content=body)
                if r.status_code < 500:
                    r.raise_for_status()
                    return
                time.sleep(0.2 * (attempt + 1))  # SQLite do Orthanc local pode recusar escrita concorrente
            raise RuntimeError(f"estudo {i}: HTTP {r.status_code} {r.text[:300]}")

        total = max(a.n, alvo_idx + 3)
        outros = [i for i in range(total) if i not in (alvo_idx, alvo_idx + 1, alvo_idx + 2)]
        with ThreadPoolExecutor(4) as pool:
            list(pool.map(send, outros))
        # alvos por último: ficam fora dos 101 primeiros que o Orthanc devolve sem filtro
        send(alvo_idx)
        send(alvo_idx + 1)
        send(alvo_idx + 2)


if __name__ == "__main__":
    main()
