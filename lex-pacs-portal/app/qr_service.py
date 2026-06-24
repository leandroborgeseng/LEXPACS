from __future__ import annotations

import logging
from typing import Any

from pydicom.dataset import Dataset

from .config import settings
from .pacs_config import _read_config, _write_config
from .qr_settings import get_qr_config, get_qr_stats, record_qr_test

logger = logging.getLogger("lex_pacs.qr")

QR_MODALITY_KEY = "LEX_QR_SMOKE"


def _orthanc_host() -> str:
    url = settings.orthanc_url.rstrip("/")
    if "://" in url:
        return url.split("://", 1)[1].split(":", 1)[0]
    return url.split(":", 1)[0]


def _orthanc_port() -> int:
    config = _read_config()
    try:
        return int(config.get("DicomPort") or 4242)
    except (TypeError, ValueError):
        return 4242


def read_qr_orthanc_settings() -> dict[str, Any]:
    config = _read_config()
    cfg = get_qr_config()
    return {
        "query_retrieve_size": int(config.get("QueryRetrieveSize") or cfg["query_retrieve_size"]),
        "dicom_always_allow_move": bool(config.get("DicomAlwaysAllowMove", False)),
        "dicom_always_allow_get": bool(config.get("DicomAlwaysAllowGet", False)),
        "dicom_always_allow_find": bool(config.get("DicomAlwaysAllowFind", False)),
    }


def apply_qr_orthanc_settings() -> dict[str, Any]:
    cfg = get_qr_config()
    config = _read_config()
    size = int(cfg["query_retrieve_size"])
    changed = False
    if config.get("QueryRetrieveSize") != size:
        config["QueryRetrieveSize"] = size
        changed = True
    for key in ("DicomAlwaysAllowMove", "DicomAlwaysAllowGet"):
        if config.get(key) is not False:
            config[key] = False
            changed = True
    if changed:
        _write_config(config)
    return read_qr_orthanc_settings()


def _ensure_smoke_consumer_modality() -> str:
    cfg = get_qr_config()
    aet = str(cfg["smoke_consumer_aet"])
    host = str(cfg["smoke_consumer_host"])
    import socket

    orthanc_host = _orthanc_host()
    orthanc_port = _orthanc_port()
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect((orthanc_host, orthanc_port))
        consumer_host = probe.getsockname()[0]
        probe.close()
    except OSError:
        try:
            consumer_host = socket.gethostbyname(host)
        except OSError:
            consumer_host = host

    config = _read_config()
    modalities = dict(config.get("DicomModalities") or {})
    entry = {
        "AET": aet,
        "Host": consumer_host,
        "Port": 4242,
        "AllowEcho": True,
        "AllowFind": True,
        "AllowMove": True,
        "AllowGet": True,
        "AllowStore": False,
    }
    key = QR_MODALITY_KEY
    if modalities.get(key) != entry:
        modalities[key] = entry
        config["DicomModalities"] = modalities
        _write_config(config)
    return aet


def build_qr_status_payload() -> dict[str, Any]:
    config = _read_config()
    modalities = config.get("DicomModalities") or {}
    consumers = []
    for key, item in modalities.items():
        if not isinstance(item, dict):
            continue
        if item.get("AllowFind") or item.get("AllowMove") or item.get("AllowGet"):
            consumers.append(
                {
                    "key": key,
                    "aet": str(item.get("AET") or ""),
                    "host": str(item.get("Host") or ""),
                    "allow_find": bool(item.get("AllowFind")),
                    "allow_move": bool(item.get("AllowMove")),
                    "allow_get": bool(item.get("AllowGet", False)),
                }
            )
    orthanc = read_qr_orthanc_settings()
    return {
        "dicom_aet": str(config.get("DicomAet") or "LEXPACS"),
        "dicom_port": int(config.get("DicomPort") or 4242),
        "orthanc": orthanc,
        "config": get_qr_config(),
        "stats": get_qr_stats(),
        "consumers": consumers,
        "consumer_count": len(consumers),
        "qr_ready": len(consumers) > 0,
    }


def test_c_find_study(*, actor: str) -> dict[str, Any]:
    calling_aet = _ensure_smoke_consumer_modality()
    called_aet = str(_read_config().get("DicomAet") or "LEXPACS")
    host = _orthanc_host()
    port = _orthanc_port()

    try:
        from pynetdicom import AE
        from pynetdicom.sop_class import StudyRootQueryRetrieveInformationModelFind
    except ImportError as exc:
        record_qr_test(actor=actor, find_count=0, success=False, error="pynetdicom ausente")
        raise RuntimeError("pynetdicom não instalado.") from exc

    ae = AE(ae_title=calling_aet)
    ae.add_requested_context(StudyRootQueryRetrieveInformationModelFind)

    identifiers = Dataset()
    identifiers.QueryRetrieveLevel = "STUDY"
    identifiers.PatientName = ""
    identifiers.PatientID = ""
    identifiers.StudyInstanceUID = ""
    identifiers.StudyDate = ""
    identifiers.AccessionNumber = ""
    identifiers.ModalitiesInStudy = ""

    count = 0
    try:
        assoc = ae.associate(host, port, ae_title=called_aet)
        if not assoc.is_established:
            record_qr_test(actor=actor, find_count=0, success=False, error="Associação DICOM rejeitada.")
            return {"success": False, "find_count": 0, "error": "Associação DICOM rejeitada."}

        responses = assoc.send_c_find(identifiers, StudyRootQueryRetrieveInformationModelFind)
        for status, _identifier in responses:
            if status and status.Status in (0xFF00, 0xFF01):
                count += 1
            elif status and status.Status not in (0x0000, 0xFF00, 0xFF01):
                assoc.release()
                msg = f"C-FIND falhou (status 0x{status.Status:04X})."
                record_qr_test(actor=actor, find_count=count, success=False, error=msg)
                return {"success": False, "find_count": count, "error": msg}
        assoc.release()
    except Exception as exc:
        logger.warning("C-FIND teste falhou: %s", exc)
        record_qr_test(actor=actor, find_count=count, success=False, error=str(exc))
        return {"success": False, "find_count": count, "error": str(exc)}

    record_qr_test(actor=actor, find_count=count, success=True)
    return {
        "success": True,
        "find_count": count,
        "calling_aet": calling_aet,
        "called_aet": called_aet,
        "host": host,
        "port": port,
    }
