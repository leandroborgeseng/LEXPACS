from __future__ import annotations

from pathlib import Path

from .config import settings

JPEG_LS_INGEST = "1.2.840.10008.1.2.4.80"


def bootstrap_ingest_transcoding() -> None:
    """Garante JPEG-LS na ingestão quando a chave foi removida (smoke E4 / mercado)."""
    try:
        from .pacs_config import _read_config, _write_config
    except Exception:
        return
    path = Path(settings.orthanc_config_path)
    if not path.is_file():
        return
    config = _read_config()
    if config.get("IngestTranscoding"):
        return
    config["IngestTranscoding"] = JPEG_LS_INGEST
    _write_config(config)


def bootstrap_runtime_files() -> None:
    bootstrap_ingest_transcoding()
