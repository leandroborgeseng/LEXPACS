"""PACS só em HTTP (sem certificado): sessão por cookie com COOKIE_SECURE=false e busca curinga inalterada."""
import hashlib
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app import local_users
from app.config import Settings, settings
from app.main import app

ROOT = Path(__file__).resolve().parents[2]
PW = "Senha-Sintetica-123"


def test_cookie_secure_padrao_false(monkeypatch):
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    assert Settings(_env_file=None).cookie_secure is False


def test_sessao_por_cookie_funciona_em_http(monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure", False)
    local_users.create_user("http.medico", PW, "medico", must_change_password=False)
    c = TestClient(app, base_url="http://pacs.local")  # HTTP puro
    r = c.post("/api/auth/clinical/login", json={"username": "http.medico", "password": PW})
    assert r.status_code == 200, r.text
    set_cookie = r.headers.get("set-cookie", "")
    assert set_cookie, "login não emitiu cookie"
    assert "secure" not in set_cookie.lower(), set_cookie  # navegador aceita e reenvia em HTTP
    assert "httponly" in set_cookie.lower()
    assert c.cookies, "cookie não guardado pelo cliente HTTP"
    me = c.get("/api/auth/clinical/me")
    assert me.status_code == 200 and me.json()["username"] == "http.medico"
    assert c.get("/api/auth/clinical/session").status_code == 200


def test_busca_curinga_inalterada():
    f = ROOT / "ohif-viewer/extensions/default/src/DicomWebDataSource/lexQidoFilters.js"
    assert hashlib.sha256(f.read_bytes()).hexdigest() == "18dabb1ba555569410830843c49a7e7f4126f28fe8cfef206f15f485dc052932"
    cfg = (ROOT / "ohif-viewer/platform/app/public/config/default.js").read_text(encoding="utf-8")
    assert "supportsWildcard: true" in cfg and "queryLimit" not in cfg
    qido = (ROOT / "ohif-viewer/extensions/default/src/DicomWebDataSource/qido.js").read_text(encoding="utf-8")
    assert "patientNameQuery(params.patientName" in qido and "exactQuery(params.patientId)" in qido
    js = (
        "import('" + f.as_uri() + "').then(m => console.log(JSON.stringify(["
        "m.patientNameQuery('Conceição'), m.patientNameQuery('co'), m.patientNameQuery('maria helena'),"
        "m.exactQuery('SINT-ALVO*')])))"
    )
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout.strip()
    assert out == '["*CONCEICAO*","CO","*MARIA*HELENA*","SINT-ALVO"]', out
