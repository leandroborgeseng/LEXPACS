"""U1–U5 — usuários locais (sintético, sem Keycloak)."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import local_users
from app.config import settings

ADMIN_PW = os.environ["LEX_ADMIN_PASSWORD"]
NEW_ADMIN_PW = "Nova-Senha-Admin-456"


def _login(client, username, password):
    return client.post("/api/auth/clinical/login", json={"username": username, "password": password})


def _admin_ready(client):
    r = _login(client, "admin", ADMIN_PW)
    assert r.status_code == 200
    r = client.post(
        "/api/auth/clinical/change-password",
        json={"current_password": ADMIN_PW, "new_password": NEW_ADMIN_PW},
    )
    assert r.status_code == 200, r.text
    return client


# ── U1 ──
def test_u1_sem_keycloak_no_codigo_e_compose():
    root = Path(__file__).resolve().parents[2]
    app_dir = root / "lex-pacs-portal" / "app"
    for py in app_dir.glob("*.py"):
        text = py.read_text(encoding="utf-8").lower()
        assert "keycloak_" not in text and "oidc_" not in text, py.name
        assert "openid-connect" not in text, py.name
    assert not (app_dir / "keycloak_admin.py").exists()
    assert not (app_dir / "clinical_oidc.py").exists()
    for name in ("docker-compose.coolify.yml", "docker-compose.externo.yml", "ohif-viewer/docker-compose.yml"):
        text = (root / name).read_text(encoding="utf-8")
        assert "quay.io/keycloak" not in text, name
        assert "KEYCLOAK_" not in text and "OIDC_" not in text, name
        assert "\n  auth:" not in text and "auth-realm-init" not in text, name
    gw = (root / "ohif-viewer/nginx/gateway.conf.template").read_text(encoding="utf-8")
    assert "location /auth/" not in gw


def test_u1_app_sobe_sem_keycloak(client):
    r = client.get("/api/auth/clinical/config")
    assert r.status_code == 200
    assert r.json()["sso_enabled"] is False


# ── U2 ──
def test_u2_perfis():
    assert local_users.PROFILES == ("admin", "medico", "tecnico", "recepcao", "paciente")


def test_u2_so_admin_cadastra(client):
    _admin_ready(client)
    r = client.post(
        "/api/admin/users",
        json={"username": "dra.teste", "full_name": "Médica Sintética", "profile": "medico", "password": "Medica-Temp-123"},
    )
    assert r.status_code == 201, r.text
    assert "password" not in r.text.lower().replace("must_change_password", "")
    # médico não cadastra
    client.post("/api/auth/clinical/logout")
    assert _login(client, "dra.teste", "Medica-Temp-123").status_code == 200
    client.post("/api/auth/clinical/change-password", json={"current_password": "Medica-Temp-123", "new_password": "Medica-Nova-456"})
    r = client.post("/api/admin/users", json={"username": "x.y", "profile": "tecnico", "password": "Qualquer-123"})
    assert r.status_code == 403
    assert client.get("/api/admin/users").status_code == 403


def test_u2_perfil_invalido_e_paciente_nao_e_interno(client):
    _admin_ready(client)
    for prof in ("root", "paciente"):
        r = client.post("/api/admin/users", json={"username": "u.ruim", "profile": prof, "password": "Senha-Valida-1"})
        assert r.status_code == 400


def test_u2_inativar_derruba_sessao(client):
    _admin_ready(client)
    client.post("/api/admin/users", json={"username": "tec.um", "profile": "tecnico", "password": "Tecnico-Temp-1"})
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as other:
        assert _login(other, "tec.um", "Tecnico-Temp-1").status_code == 200
        other.post("/api/auth/clinical/change-password", json={"current_password": "Tecnico-Temp-1", "new_password": "Tecnico-Nova-2"})
        assert other.get("/api/auth/validate-clinical").status_code == 200
        assert client.post("/api/admin/users/tec.um/deactivate").status_code == 200
        assert other.get("/api/auth/validate-clinical").status_code == 401
        assert _login(other, "tec.um", "Tecnico-Nova-2").status_code == 401


def test_u2_tela_admin_existe(client):
    r = client.get("/clinica/usuarios")
    assert r.status_code == 200 and "Usuários internos" in r.text


# ── U3 ──
def test_u3_hash_argon2_e_minimo_10():
    local_users.create_user("hash.teste", "Abcdef-1234", "tecnico")
    import sqlite3

    row = sqlite3.connect(settings.local_users_db_path).execute(
        "SELECT password_hash FROM users WHERE username='hash.teste'"
    ).fetchone()
    assert row[0].startswith("$argon2id$")
    assert "Abcdef-1234" not in row[0]
    with pytest.raises(local_users.UserError):
        local_users.create_user("curta.teste", "123456789", "tecnico")


def test_u3_senha_nunca_em_log_ou_resposta(client):
    _admin_ready(client)
    secret = "Segredo-Unico-987"
    r = client.post("/api/admin/users", json={"username": "rec.um", "profile": "recepcao", "password": secret})
    assert secret not in r.text
    assert secret not in client.get("/api/admin/users").text
    _login(client, "rec.um", "errada-" + secret)
    audit = Path(settings.audit_data_path) / "audit.jsonl"
    content = audit.read_text(encoding="utf-8")
    assert secret not in content and NEW_ADMIN_PW not in content and ADMIN_PW not in content


# ── U4 ──
def test_u4_bloqueio_5_tentativas_15_min(client):
    local_users.create_user("bloq.teste", "Correta-12345", "tecnico")
    for _ in range(4):
        assert _login(client, "bloq.teste", "errada-000000").status_code == 401
    assert _login(client, "bloq.teste", "errada-000000").status_code == 423
    # mesmo com a senha certa continua bloqueado
    assert _login(client, "bloq.teste", "Correta-12345").status_code == 423
    # passados 15 min, libera
    import sqlite3

    past = (datetime.now(timezone.utc) - timedelta(seconds=1)).replace(microsecond=0).isoformat()
    conn = sqlite3.connect(settings.local_users_db_path)
    lu = conn.execute("SELECT locked_until FROM users WHERE username='bloq.teste'").fetchone()[0]
    delta = datetime.fromisoformat(lu) - datetime.now(timezone.utc)
    assert timedelta(minutes=14) < delta <= timedelta(minutes=15)
    conn.execute("UPDATE users SET locked_until=? WHERE username='bloq.teste'", (past,))
    conn.commit()
    assert _login(client, "bloq.teste", "Correta-12345").status_code == 200


def test_u4_sessao_expira_por_inatividade_30_min(client):
    assert settings.session_idle_minutes == 30
    local_users.create_user("idle.teste", "Correta-12345", "medico", must_change_password=False)
    assert _login(client, "idle.teste", "Correta-12345").status_code == 200
    assert client.get("/api/auth/validate-clinical").status_code == 200
    import sqlite3

    old = (datetime.now(timezone.utc) - timedelta(minutes=31)).replace(microsecond=0).isoformat()
    conn = sqlite3.connect(settings.local_users_db_path)
    conn.execute("UPDATE sessions SET last_seen=?", (old,))
    conn.commit()
    assert client.get("/api/auth/validate-clinical").status_code == 401
    assert client.get("/api/auth/validate-dicom-access").status_code == 401


def test_u4_logout_invalida_sessao(client):
    local_users.create_user("out.teste", "Correta-12345", "medico", must_change_password=False)
    r = _login(client, "out.teste", "Correta-12345")
    token = r.json()["access_token"]
    client.post("/api/auth/clinical/logout")
    r = client.get("/api/auth/validate-clinical", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


# ── U5 ──
def test_u5_admin_inicial_por_env_com_troca_obrigatoria(client):
    r = _login(client, "admin", ADMIN_PW)
    assert r.status_code == 200
    body = r.json()
    assert body["must_change_password"] is True
    assert body["redirect_url"] == "/clinica/senha"
    # enquanto não troca: sem admin, sem viewer, sem DICOMweb
    assert client.get("/api/admin/users").status_code == 403
    assert client.get("/api/auth/validate-dicom-access").status_code == 401
    assert client.get("/api/auth/validate-clinical").status_code == 401
    assert client.get("/api/auth/clinical/me").json()["must_change_password"] is True
    # senha curta recusada
    r = client.post("/api/auth/clinical/change-password", json={"current_password": ADMIN_PW, "new_password": "curta"})
    assert r.status_code == 400
    r = client.post("/api/auth/clinical/change-password", json={"current_password": ADMIN_PW, "new_password": NEW_ADMIN_PW})
    assert r.status_code == 200
    assert client.get("/api/admin/users").status_code == 200
    assert client.get("/api/auth/validate-dicom-access").status_code == 200


def test_u5_bootstrap_nao_recria_se_ja_ha_usuarios():
    assert local_users.bootstrap_admin() is True
    assert local_users.bootstrap_admin() is False


def test_auditoria_login_e_cadastro(client):
    _admin_ready(client)
    client.post("/api/admin/users", json={"username": "aud.um", "profile": "tecnico", "password": "Tecnico-Temp-1"})
    audit = Path(settings.audit_data_path) / "audit.jsonl"
    events = [json.loads(line)["event"] for line in audit.read_text(encoding="utf-8").splitlines() if line]
    assert "clinical_login" in events and "user_create" in events and "clinical_password_changed" in events


def test_locales_sem_keycloak_ad():
    root = Path(__file__).resolve().parents[2]
    files = list((root / "locales").glob("*/*.json")) + list((root / "lex-pacs-portal/static/locales").glob("*/*.json"))
    assert files
    for f in files:
        text = f.read_text(encoding="utf-8").lower()
        json.loads(text)
        for word in ("keycloak", "active directory", "ldap"):
            assert word not in text, (f.name, word)
