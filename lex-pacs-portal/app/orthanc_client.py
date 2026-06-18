from __future__ import annotations

import httpx

from .config import settings


class OrthancClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.orthanc_url).rstrip("/")

    async def find_patients_by_id(self, patient_id: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/tools/find",
                json={"Level": "Patient", "Query": {"PatientID": patient_id}},
            )
            response.raise_for_status()
            orthanc_ids = response.json()

            patients: list[dict] = []
            for orthanc_id in orthanc_ids:
                detail = await client.get(f"{self.base_url}/patients/{orthanc_id}")
                detail.raise_for_status()
                tags = detail.json().get("MainDicomTags", {})
                patients.append(
                    {
                        "orthanc_id": orthanc_id,
                        "patient_id": tags.get("PatientID", ""),
                        "patient_name": tags.get("PatientName", ""),
                        "birth_date": tags.get("PatientBirthDate", ""),
                        "sex": tags.get("PatientSex", ""),
                    }
                )
            return patients

    async def find_studies_for_patient(self, patient_id: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/tools/find",
                json={"Level": "Study", "Query": {"PatientID": patient_id}},
            )
            response.raise_for_status()
            study_ids = response.json()

            studies: list[dict] = []
            for study_id in study_ids:
                detail = await client.get(f"{self.base_url}/studies/{study_id}")
                detail.raise_for_status()
                payload = detail.json()
                tags = payload.get("MainDicomTags", {})
                patient_tags = payload.get("PatientMainDicomTags", {})
                studies.append(
                    {
                        "study_instance_uid": tags.get("StudyInstanceUID", ""),
                        "study_date": tags.get("StudyDate", ""),
                        "study_description": tags.get("StudyDescription", ""),
                        "accession_number": tags.get("AccessionNumber", ""),
                        "modalities": payload.get("ModalitiesInStudy", []),
                        "series_count": len(payload.get("Series", [])),
                        "instance_count": payload.get("CountInstances", 0),
                        "patient_name": patient_tags.get("PatientName", ""),
                    }
                )
            return studies
