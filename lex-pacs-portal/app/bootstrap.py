from __future__ import annotations

from pathlib import Path

from passlib.apache import HtpasswdFile

from .config import settings

JPEG_LS_INGEST = "1.2.840.10008.1.2.4.80"


def bootstrap_htpasswd() -> None:
    """Cria htpasswd inicial a partir de env (Coolify) se o arquivo ainda não existir."""
    path = Path(settings.clinical_htpasswd_path)
    user = settings.clinical_bootstrap_user.strip()
    password = settings.clinical_bootstrap_password
    if not user or not password:
        return
    if path.is_file() and path.stat().st_size > 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    ht = HtpasswdFile(str(path), new=True)
    ht.set_password(user, password)
    ht.save()
    path.chmod(0o600)


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
    bootstrap_htpasswd()
    bootstrap_ingest_transcoding()
