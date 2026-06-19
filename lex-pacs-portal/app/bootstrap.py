from __future__ import annotations

from pathlib import Path

from passlib.apache import HtpasswdFile

from .config import settings


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


def bootstrap_runtime_files() -> None:
    bootstrap_htpasswd()
