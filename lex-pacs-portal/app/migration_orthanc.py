from __future__ import annotations

import json
import time
from typing import Any

import httpx

from .config import settings
from .migration_store import MIGRATION_MODALITY_KEY

JOB_POLL_INTERVAL = 2.0
JOB_TIMEOUT = 600.0


class MigrationOrthancError(RuntimeError):
    pass


def _client() -> httpx.Client:
    return httpx.Client(base_url=settings.orthanc_url.rstrip("/"), timeout=120.0)


def get_local_aet() -> str:
    with _client() as client:
        response = client.get("/system")
        response.raise_for_status()
        return str(response.json().get("DicomAet") or "LEXPACS")


def modality_echo(modality_key: str = MIGRATION_MODALITY_KEY) -> dict[str, Any]:
    with _client() as client:
        response = client.post(f"/modalities/{modality_key}/echo")
        if response.status_code >= 400:
            raise MigrationOrthancError(response.text[:240] or "C-ECHO falhou")
        return response.json()


def _build_study_query(filters: dict[str, Any]) -> dict[str, str]:
    query: dict[str, str] = {}
    patient_id = str(filters.get("patient_id") or "").strip()
    modality = str(filters.get("modality") or "").strip()
    date_from = str(filters.get("study_date_from") or "").strip()
    date_to = str(filters.get("study_date_to") or "").strip()
    if patient_id:
        query["PatientID"] = patient_id
    if modality:
        query["ModalitiesInStudy"] = modality
    if date_from and date_to:
        query["StudyDate"] = f"{date_from}-{date_to}"
    elif date_from:
        query["StudyDate"] = f"{date_from}-"
    elif date_to:
        query["StudyDate"] = f"-{date_to}"
    return query


def discover_remote_studies(
    filters: dict[str, Any],
    modality_key: str = MIGRATION_MODALITY_KEY,
) -> list[dict[str, Any]]:
    query = _build_study_query(filters)
    with _client() as client:
        response = client.post(
            f"/modalities/{modality_key}/query",
            json={"Level": "Study", "Query": query},
        )
        if response.status_code >= 400:
            raise MigrationOrthancError(response.text[:240] or "C-FIND remoto falhou")
        query_id = response.json().get("ID")
        if not query_id:
            raise MigrationOrthancError("Resposta C-FIND sem ID de query.")

        answers_resp = client.get(f"/queries/{query_id}/answers")
        answers_resp.raise_for_status()
        indices = answers_resp.json()
        if not isinstance(indices, list):
            raise MigrationOrthancError("Resposta de answers inválida.")

        studies: list[dict[str, Any]] = []
        for index in indices:
            content_resp = client.get(f"/queries/{query_id}/answers/{index}/content")
            if content_resp.status_code >= 400:
                continue
            tags = content_resp.json()
            uid = str(tags.get("StudyInstanceUID") or "").strip()
            if not uid:
                continue
            studies.append(
                {
                    "study_instance_uid": uid,
                    "patient_id": str(tags.get("PatientID") or ""),
                    "patient_name": str(tags.get("PatientName") or ""),
                    "study_date": str(tags.get("StudyDate") or ""),
                    "study_description": str(tags.get("StudyDescription") or ""),
                    "accession_number": str(tags.get("AccessionNumber") or ""),
                    "modalities": str(tags.get("ModalitiesInStudy") or ""),
                }
            )
        return studies


def study_exists_locally(study_instance_uid: str) -> bool:
    with _client() as client:
        response = client.post(
            "/tools/find",
            json={"Level": "Study", "Query": {"StudyInstanceUID": study_instance_uid}},
        )
        response.raise_for_status()
        return bool(response.json())


def retrieve_remote_study(
    study_instance_uid: str,
    modality_key: str = MIGRATION_MODALITY_KEY,
) -> int:
    local_aet = get_local_aet()
    with _client() as client:
        response = client.post(
            f"/modalities/{modality_key}/query",
            json={
                "Level": "Study",
                "Query": {"StudyInstanceUID": study_instance_uid},
            },
        )
        if response.status_code >= 400:
            raise MigrationOrthancError(response.text[:240] or "C-FIND do estudo falhou")
        query_id = response.json().get("ID")
        if not query_id:
            raise MigrationOrthancError("Query do estudo sem ID.")

        answers_resp = client.get(f"/queries/{query_id}/answers")
        answers_resp.raise_for_status()
        indices = answers_resp.json()
        if not indices:
            raise MigrationOrthancError("Estudo não encontrado no PACS remoto.")

        before = _count_instances(client)
        retrieve_resp = client.post(
            f"/queries/{query_id}/answers/{indices[0]}/retrieve",
            json={"TargetAet": local_aet, "Synchronous": False},
        )
        if retrieve_resp.status_code >= 400:
            raise MigrationOrthancError(retrieve_resp.text[:240] or "C-MOVE falhou")

        job_id = retrieve_resp.json().get("ID")
        if not job_id:
            raise MigrationOrthancError("Retrieve sem job ID.")

        _wait_job(client, str(job_id))
        after = _count_instances(client)
        return max(0, after - before)


def _count_instances(client: httpx.Client) -> int:
    response = client.get("/statistics")
    if response.status_code >= 400:
        return 0
    return int(response.json().get("CountInstances") or 0)


def _wait_job(client: httpx.Client, job_id: str) -> None:
    deadline = time.monotonic() + JOB_TIMEOUT
    while time.monotonic() < deadline:
        response = client.get(f"/jobs/{job_id}")
        response.raise_for_status()
        payload = response.json()
        state = str(payload.get("State") or "")
        if state == "Success":
            return
        if state in {"Failure", "Paused"}:
            content = payload.get("Content") or {}
            error = content.get("ErrorDescription") or content.get("Description") or state
            raise MigrationOrthancError(str(error)[:240])
        time.sleep(JOB_POLL_INTERVAL)
    raise MigrationOrthancError("Timeout aguardando job DICOM.")
