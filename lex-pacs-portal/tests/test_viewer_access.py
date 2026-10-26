"""V1–V3 — viewer/DICOMweb (Orthanc só por env, só leitura, sem sessão = 401)."""
import re
from pathlib import Path

import httpx
import pytest

from app import local_users

ROOT = Path(__file__).resolve().parents[2]
GATEWAY = (ROOT / "ohif-viewer/nginx/gateway.conf.template").read_text(encoding="utf-8")
PUBLIC_IP = re.compile(r"\b(?!10\.|127\.|172\.(?:1[6-9]|2\d|3[01])\.|192\.168\.)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")


def _location(name: str) -> str:
    m = re.search(r"    location %s \{\n(.*?)\n    \}\n" % re.escape(name), GATEWAY, re.S)
    assert m, name
    return m.group(1)


# ── V1 ──
def test_v1_orthanc_so_por_env_no_codigo():
    from app.config import Settings

    assert Settings.model_fields["orthanc_url"].default == ""
    assert "orthanc_username" in Settings.model_fields and "orthanc_password" in Settings.model_fields


def test_v1_sem_ip_publico_hardcoded():
    files = [
        "docker-compose.coolify.yml",
        "docker-compose.externo.yml",
        "ohif-viewer/docker-compose.yml",
        "ohif-viewer/nginx/gateway.conf.template",
        ".env.externo.example",
        ".env.coolify.example",
    ]
    for name in files:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "189.90.139.222" not in text, name
        assert not PUBLIC_IP.findall(text), (name, PUBLIC_IP.findall(text))


def test_v1_gateway_usa_env_para_orthanc():
    assert "${LEX_ORTHANC_URL}" in GATEWAY
    assert "${LEX_ORTHANC_AUTH_HEADER}" in GATEWAY
    assert "server:8042" not in GATEWAY
    for loc in ("/dicom-web", "/wado"):
        body = _location(loc)
        assert "proxy_pass $lex_orthanc_url$request_uri;" in body


def test_v1_compose_externo_exige_orthanc_url():
    text = (ROOT / "docker-compose.externo.yml").read_text(encoding="utf-8")
    assert "${ORTHANC_URL:?" in text
    assert "\n  server:" not in text and "\n  database:" not in text and "docker.sock" not in text


@pytest.mark.asyncio
async def test_v1_orthanc_client_usa_basic_auth_do_env(monkeypatch):
    from app import orthanc_client
    from app.config import settings

    monkeypatch.setattr(settings, "orthanc_username", "leitor")
    monkeypatch.setattr(settings, "orthanc_password", "senha-de-teste")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["url"] = str(request.url)
        return httpx.Response(200, json=[])

    real = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(orthanc_client.httpx, "AsyncClient", fake_client)
    await orthanc_client.OrthancClient("http://orthanc-mock.invalid:8042").find_studies_for_patient("SINT-0001")
    assert seen["auth"].startswith("Basic ")
    assert seen["url"].startswith("http://orthanc-mock.invalid:8042/")


# ── V2 ──
def test_v2_dicomweb_somente_leitura():
    for loc in ("/dicom-web", "/wado"):
        body = _location(loc)
        assert re.search(r"limit_except GET \{\s*deny all;\s*\}", body), loc
        assert "proxy_set_header Authorization $lex_orthanc_auth;" in body
        assert 'proxy_set_header Cookie "";' in body


def test_v2_startup_nao_altera_orthanc_externo(monkeypatch, client):
    from app.config import settings

    assert settings.orthanc_external_readonly is True


# ── V3 ──
def test_v3_sem_sessao_401(client):
    assert client.get("/api/auth/validate-dicom-access").status_code == 401
    assert client.get("/api/auth/validate-clinical").status_code == 401
    assert client.get("/api/auth/validate-dicom-access", headers={"Authorization": "Bearer lixo"}).status_code == 401


def test_v3_dicomweb_401_sem_redirect():
    for loc in ("/dicom-web", "/wado"):
        body = _location(loc)
        assert "auth_request /internal/auth/dicom-access;" in body
        assert "error_page 401" not in body


def test_v3_recepcao_nao_ve_imagens(client):
    local_users.create_user("rec.img", "Recepcao-1234", "recepcao", must_change_password=False)
    client.post("/api/auth/clinical/login", json={"username": "rec.img", "password": "Recepcao-1234"})
    assert client.get("/api/auth/validate-dicom-access").status_code == 401


def test_v3_medico_ve_imagens(client):
    local_users.create_user("med.img", "Medico-12345", "medico", must_change_password=False)
    client.post("/api/auth/clinical/login", json={"username": "med.img", "password": "Medico-12345"})
    r = client.get("/api/auth/validate-dicom-access")
    assert r.status_code == 200 and r.headers["x-clinic-groups"] == "medico"


def test_v3_orthanc_sem_porta_publicada_no_compose_externo():
    text = (ROOT / "docker-compose.externo.yml").read_text(encoding="utf-8")
    assert "8042:" not in text
