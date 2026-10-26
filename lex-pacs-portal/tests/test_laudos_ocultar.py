"""LD1–LD5 — LEX_LAUDOS_HABILITADO (padrão false): laudos ocultos, API 404, nada apagado."""
import hashlib
import re
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import local_users, reports
from app.auth import create_access_token
from app.config import settings
from app.laudos_feature import is_laudo_path
from app.main import app
from app.report_storage import save_draft

ROOT = Path(__file__).resolve().parents[2]
UIDS = ("1.2.826.0.1.3680043.8.498.101", "1.2.826.0.1.3680043.8.498.102")
PW = "Senha-Sintetica-123"
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")


def _snapshot() -> dict:
    base = Path(settings.reports_data_path)
    return {
        str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(base.rglob("*"))
        if p.is_file()
    }


@pytest.fixture
def laudos_existentes():
    for uid in UIDS:
        save_draft(uid, f"<p>Laudo sintético {uid}</p>", "Dra. Sintética")
    snap = _snapshot()
    assert len([k for k in snap if k.endswith("report.json")]) >= len(UIDS)
    return snap


def _session(profile: str) -> TestClient:
    username = f"ld.{profile}"
    local_users.create_user(username, PW, profile, must_change_password=False)
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post("/api/auth/clinical/login", json={"username": username, "password": PW})
    assert r.status_code == 200, r.text
    return c


def _patient_headers() -> dict:
    return {"Authorization": f"Bearer {create_access_token('SINT-PAC-1', 'PACIENTE^SINTETICO')}"}


def _laudo_routes():
    out = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        is_laudo = (
            route.endpoint.__module__ == reports.__name__
            or re.search(r"report", route.path, re.I)
            or re.search(r"report|laudo", route.endpoint.__name__, re.I)
        )
        if is_laudo:
            path = re.sub(r"\{[^}]+\}", UIDS[0], route.path)
            out.append((path, sorted(route.methods)))
    return out


def _alt_paths():
    u = UIDS[0]
    return [
        f"/api/reports/{u}", f"/api/reports/{u}/", f"//api/reports/{u}", f"/api//reports/{u}",
        f"/API/REPORTS/{u}", f"/api/Reports/{u}/pdf", f"/api/reports/{u}/pdf?download=1",
        f"/api/reports/{u}/sign", f"/api/reports/{u}/release", f"/api/reports/{u}/revoke-patient",
        "/api/reports", "/api/reports/", f"/api/studies/{u}/report", f"/api/studies/{u}/report/",
        f"/api/studies/{u}/report/pdf", f"/api/studies/{u}//report/pdf", f"/API/studies/{u}/REPORT",
    ]


@pytest.fixture
def desligado(monkeypatch):
    monkeypatch.setattr(settings, "lex_laudos_habilitado", False)


@pytest.fixture
def ligado(monkeypatch):
    monkeypatch.setattr(settings, "lex_laudos_habilitado", True)

    async def _ok(_uid):
        return None

    monkeypatch.setattr(reports, "_ensure_study_exists", _ok)


def test_ld_padrao_e_false_sem_variavel(monkeypatch):
    monkeypatch.delenv("LEX_LAUDOS_HABILITADO", raising=False)
    from app.config import Settings

    assert Settings(_env_file=None).lex_laudos_habilitado is False


def test_ld2_router_inteiro_404_qualquer_metodo_e_sessao(desligado, laudos_existentes):
    rotas = _laudo_routes()
    caminhos = {p for p, _ in rotas}
    # get por id, PUT, assinar, PDF (gerar/baixar), liberar/revogar e rotas do paciente
    for esperado in ("/api/reports/{u}", "/api/reports/{u}/sign", "/api/reports/{u}/pdf",
                     "/api/reports/{u}/release", "/api/reports/{u}/revoke-patient",
                     "/api/studies/{u}/report", "/api/studies/{u}/report/pdf"):
        assert esperado.format(u=UIDS[0]) in caminhos, esperado
    admin, medico = _session("admin"), _session("medico")
    anon = TestClient(app, raise_server_exceptions=False)
    for path, _methods in rotas:
        assert is_laudo_path(path), f"rota de laudo fora do filtro: {path}"
    alvos = [p for p, _ in rotas] + _alt_paths()
    for path in alvos:
        for method in METHODS:
            for nome, c, h in (("admin", admin, {}), ("medico", medico, {}), ("anon", anon, {}),
                               ("paciente", anon, _patient_headers())):
                r = c.request(method, path, headers=h, json={"content_html": "x", "signed_by": "x"})
                assert r.status_code == 404, (nome, method, path, r.status_code)
                assert b"Laudo" not in r.content and b"laudo" not in r.content
    assert _snapshot() == laudos_existentes  # LD3: contagem e conteúdo iguais


def test_ld2_gateway_aliases_caem_nas_rotas_do_portal():
    gw = (ROOT / "ohif-viewer/nginx/gateway.conf.template").read_text(encoding="utf-8")
    # /clinica-api/* e /paciente-api/* só chegam ao portal reescritos para /api/* (onde o filtro atua)
    for rw in re.findall(r"rewrite\s+(\S+)\s+(\S+)", gw):
        if "clinica-api" in rw[0] or "paciente-api" in rw[0]:
            assert rw[1] == "/api/$1", rw
    assert not re.search(r"proxy_pass\s+\S*/(reports|lex-reports)", gw)


def test_ld3_sem_migration_nem_delete_de_laudos():
    src = (ROOT / "lex-pacs-portal/app/laudos_feature.py").read_text(encoding="utf-8")
    assert not re.search(r"unlink|rmtree|remove\(|DELETE|os\.rm", src)


def test_ld1_ld4_me_informa_laudos_visivel(desligado):
    for prof in ("admin", "medico", "tecnico", "recepcao"):
        r = _session(prof).get("/api/auth/clinical/me")
        assert r.status_code == 200 and r.json()["laudos_visivel"] is False, prof


def test_ld4_ligado_so_can_draft_ou_can_sign(ligado, laudos_existentes):
    esperado = {"admin": True, "medico": True, "tecnico": True, "recepcao": False}
    for prof, pode in esperado.items():
        c = _session(prof)
        perms = c.get("/api/auth/clinical/me").json()
        assert perms["laudos_visivel"] is pode, prof
        assert pode == bool(perms["permissions"]["can_draft"] or perms["permissions"]["can_sign"])
        r = c.get(f"/api/reports/{UIDS[0]}")
        if pode:
            assert r.status_code == 200, (prof, r.text)
        else:
            assert r.status_code == 403, (prof, r.status_code)
            assert c.put(f"/api/reports/{UIDS[0]}", json={"content_html": "x"}).status_code == 403
            assert c.post(f"/api/reports/{UIDS[0]}/sign", json={"signed_by": "x"}).status_code == 403
    anon = TestClient(app, raise_server_exceptions=False)
    assert anon.get(f"/api/reports/{UIDS[0]}").status_code in (401, 403)
    assert _snapshot() == laudos_existentes


def test_ld5_portal_paciente_sem_laudo(desligado, monkeypatch):
    from app import main

    async def _studies(_pid):
        return [{"study_instance_uid": UIDS[0], "study_description": "TC", "report_available": True}]

    monkeypatch.setattr(main.orthanc, "find_studies_for_patient", _studies)
    r = TestClient(app).get("/api/studies", headers=_patient_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["laudos_habilitado"] is False
    assert all("report" not in k for s in body["studies"] for k in s)
    js = (ROOT / "lex-pacs-portal/static/portal.js").read_text(encoding="utf-8")
    assert "reportView.remove();" in js and "laudosHabilitado && study.report_available" in js
    for loc in ("pt-BR", "en-US", "es"):
        hint = (ROOT / f"lex-pacs-portal/static/locales/{loc}/Portal.json").read_text(encoding="utf-8")
        linha = next(ln for ln in hint.splitlines() if "\"hint\"" in ln)
        assert not re.search(r"laudo|report|el informe", linha, re.I), (loc, linha)


def test_traefik_todo_router_sem_access_log():
    compose = (ROOT / "docker-compose.coolify.yml").read_text(encoding="utf-8")
    routers = set(re.findall(r"traefik\.http\.routers\.([A-Za-z0-9_-]+)\.", compose))
    assert routers, "nenhum router Traefik declarado"
    for r in routers:
        assert f'"traefik.http.routers.{r}.observability.accesslogs=false"' in compose, r
    assert "accesslogs=true" not in compose
