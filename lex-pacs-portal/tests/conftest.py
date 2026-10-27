import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="lexpacs-test-")
os.environ.setdefault("LOCAL_USERS_DB_PATH", str(Path(_TMP) / "users.db"))
os.environ.setdefault("AUDIT_DATA_PATH", str(Path(_TMP) / "audit"))
os.environ.setdefault("REPORTS_DATA_PATH", str(Path(_TMP) / "reports"))
os.environ.setdefault("ORTHANC_URL", "http://orthanc-mock.invalid:8042")
os.environ.setdefault("ORTHANC_EXTERNAL_READONLY", "true")
os.environ.setdefault("JWT_SECRET", "test-secret-nao-usar-em-producao-123456")
os.environ.setdefault("LEX_ADMIN_USER", "admin")
os.environ.setdefault("LEX_ADMIN_PASSWORD", "Senha-Inicial-123")
os.environ.setdefault("LOGIN_RATE_LIMIT_ATTEMPTS", "10000")
os.environ.setdefault("WORKLIST_INDEX_AUTOSTART", "false")
os.environ.setdefault("WORKLIST_INDEX_AUTO_RETRY", "false")  # testes ligam o timer explicitamente  # sem thread contra o Orthanc fictício

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_db():
    from app import local_users

    path = Path(os.environ["LOCAL_USERS_DB_PATH"])
    if path.exists():
        path.unlink()
    from app import rate_limit

    rate_limit._hits.clear()
    local_users.init_db()
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
