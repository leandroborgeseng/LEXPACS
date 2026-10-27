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


# ── Revisão QA (ciclo 1): rotas admin e allowlist do portal do paciente ──
def _admin_routes():
    from fastapi.routing import APIRoute

    from app.main import app

    routes = []
    for r in app.routes:
        if isinstance(r, APIRoute) and r.path.startswith("/api/admin"):
            for m in r.methods - {"HEAD", "OPTIONS"}:
                routes.append((m, r.path.replace("{username}", "alguem.teste")))
    return routes


def test_todas_rotas_admin_existem():
    paths = {p for _, p in _admin_routes()}
    for p in ("/api/admin/pacs/settings", "/api/admin/pacs/settings/aet", "/api/admin/pacs/equipment",
              "/api/admin/pacs/worklist-views", "/api/admin/users"):
        assert p in paths
    assert len(_admin_routes()) > 40


def test_todas_rotas_admin_401_sem_sessao(client):
    for method, path in _admin_routes():
        r = client.request(method, path, json={})
        assert r.status_code == 401, (method, path, r.status_code)


@pytest.mark.parametrize("profile", ["medico", "tecnico", "recepcao"])
def test_todas_rotas_admin_403_nao_admin(client, profile):
    local_users.create_user(f"{profile}.qa", "Senha-QA-12345", profile, must_change_password=False)
    assert client.post("/api/auth/clinical/login", json={"username": f"{profile}.qa", "password": "Senha-QA-12345"}).status_code == 200
    for method, path in _admin_routes():
        r = client.request(method, path, json={})
        assert r.status_code == 403, (profile, method, path, r.status_code)


def _paciente_locations():
    return re.findall(r"    location (=|~|) ?\"?(\^?/paciente-api/[^\s\"]*)\"? \{\n(.*?)\n    \}\n", GATEWAY, re.S)


def test_gateway_paciente_api_so_allowlist():
    allow = re.compile(r"^/paciente-api/(auth/login|studies|studies/[0-9.]+/(report|report/pdf|viewer-session))$")
    proxied = []
    for kind, path, body in _paciente_locations():
        if "proxy_pass" in body:
            assert kind in ("=", "~"), path  # sem prefixo genérico
            proxied.append((kind, path))
        else:
            assert "return 404" in body, path
    assert ("", "/paciente-api/") not in proxied
    regexes = [re.compile(p) for k, p in proxied if k == "~"]
    exacts = {p for k, p in proxied if k == "="}
    def is_proxied(uri):
        return uri in exacts or any(rx.match(uri) for rx in regexes)
    for uri in ("/paciente-api/admin/pacs/settings", "/paciente-api/admin/users", "/paciente-api/reports/1.2.3",
                "/paciente-api/auth/clinical/me", "/paciente-api/health", "/paciente-api/studies/1.2/../../admin"):
        assert not is_proxied(uri), uri
    for uri in ("/paciente-api/auth/login", "/paciente-api/studies", "/paciente-api/studies/1.2.3/report",
                "/paciente-api/studies/1.2.3/report/pdf", "/paciente-api/studies/1.2.3/viewer-session"):
        assert is_proxied(uri) and allow.match(uri), uri


# ── LP9 (parcial): access log do gateway sem query string nem Referer ──
def test_lp9_log_format_sem_query_string():
    sec = (ROOT / "ohif-viewer/nginx/00-lex-security.conf").read_text(encoding="utf-8")
    m = re.search(r"log_format lex_sem_args (.*?);", sec, re.S)
    assert m, "log_format lex_sem_args ausente"
    fmt = m.group(1)
    assert "$uri" in fmt
    for proibido in ("$request ", "$request\"", "$request_uri", "$args", "$query_string", "$http_referer", "$arg_"):
        assert proibido not in fmt, proibido
    server_head = GATEWAY.split("location", 1)[0]
    assert "access_log /var/log/nginx/access.log lex_sem_args;" in server_head
    assert "access_log" not in GATEWAY.split("location", 1)[1]  # nenhum location volta ao formato padrão


def test_lp4_datasource_curinga_ligado_e_querylimit_inalterado():
    cfg = (ROOT / "ohif-viewer/platform/app/public/config/default.js").read_text(encoding="utf-8")
    assert "supportsWildcard: true" in cfg
    assert "queryLimit" not in cfg  # continua o padrão do OHIF (101)
    qido_js = (ROOT / "ohif-viewer/extensions/default/src/DicomWebDataSource/qido.js").read_text(encoding="utf-8")
    assert "patientNameQuery(params.patientName" in qido_js
    assert "exactQuery(params.patientId)" in qido_js


# ── Cache do viewer: só bundles com hash são immutable ──
SEC = (ROOT / "ohif-viewer/nginx/00-lex-security.conf").read_text(encoding="utf-8")


def _viewer_cache(request_uri: str) -> str:
    """Avalia o map $lex_viewer_cache_control como o nginx: 1ª regex que casa, na ordem."""
    body = re.search(r"map \$request_uri \$lex_viewer_cache_control \{\n(.*?)\n\}", SEC, re.S).group(1)
    default = ""
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'"~(.+)"\s+"(.*)";$', line)
        if m:
            if re.search(m.group(1), request_uri):
                return m.group(2)
            continue
        d = re.match(r'default\s+"(.*)";$', line)
        assert d, line
        default = d.group(1)
    return default


@pytest.mark.parametrize("uri", ["/viewer/app-config.js", "/viewer/app-config.js?v=3", "/viewer/sw.js",
                                 "/viewer/init-service-worker.js", "/viewer/manifest.json", "/viewer/index.html",
                                 "/viewer/", "/viewer", "/viewer/?x=1", "/viewer/viewer/dicomweb", "/viewer/app.bundle.css"])
def test_viewer_no_cache_em_config_sw_manifest_e_index(uri):
    assert _viewer_cache(uri) == "no-cache", uri


@pytest.mark.parametrize("uri", ["/viewer/app.bundle.125f92a65e0d229a.js", "/viewer/9356.bundle.2723c0ba18d58936.js",
                                 "/viewer/06ac09dcb8ec7d56.woff2", "/viewer/0ddf166f7a343eda.wasm",
                                 "/viewer/100.bundle.1c8cd7171c2c3336.js.map".replace(".js.map", ".js")])
def test_viewer_immutable_so_em_bundle_com_hash(uri):
    assert _viewer_cache(uri) == "public, max-age=31536000, immutable", uri


@pytest.mark.parametrize("uri", ["/clinica/", "/dicom-web/studies", "/static/app.js", "/"])
def test_cache_control_do_viewer_nao_vaza_para_outras_rotas(uri):
    assert _viewer_cache(uri) == ""


def test_gateway_aplica_cache_no_server_e_mantem_auth_como_antes():
    head = GATEWAY.split("\n    location", 1)[0]
    assert "add_header Cache-Control $lex_viewer_cache_control always;" in head
    assert '"public, max-age=31536000, immutable"' not in GATEWAY  # nada fixo num location
    static = _location(r"~ ^/viewer/(.+\.(?:js|css|map|svg|png|jpe?g|gif|webp|ico|woff2?|ttf|eot|wasm|json|webmanifest|txt))$")
    assert "auth_request" not in static and "add_header" not in static  # assets sem login, herdam segurança
    assert "proxy_hide_header Cache-Control;" in static
    for name in ("/viewer/", "= /viewer"):
        loc = _location(name)
        assert "auth_request /internal/auth/dicom-access;" in loc and "add_header" not in loc
        assert "proxy_hide_header Cache-Control;" in loc
