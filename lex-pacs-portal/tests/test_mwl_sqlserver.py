"""MW-A1, A2, A4, A5 e A6 contra SQL Server em container. Só dados sintéticos.

A senha do SA e a do usuário só leitura vêm de MSSQL_SA_PASSWORD e LEX_MWL_SQL_PASSWORD.
Se as variáveis não existirem, o teste gera um valor só na memória do processo e no `docker run -e`,
sem gravar senha no repositório. Nomes de paciente são fictícios (prefixo ZZSINT).

Suposição de origem (P2 ainda não confirmada pelo hospital): a coluna de status, a coluna de data
e os valores de cancelado/realizado vêm do mapeamento. Neste teste os nomes são sintéticos
(situacao, data_exame, CANCELADA, CONCLUIDO) para provar que o código não depende do esquema real.
"""
from __future__ import annotations

import os
import secrets
import subprocess
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.config import settings
from app.mwl_scheduler import run_mwl_sync
from app.mwl_sql import get_mwl_sync_meta, save_mwl_sql_config

pytestmark = pytest.mark.mssql

CONTAINER = "lex-mwl-mssql-sint"
DATABASE = "lexmwl_sint"
RO_USER = "lex_mwl_ro"
PATIENT = "ZZSINT^JOÃO CONCEIÇÃO"
PATIENT_ID = "SINT-PID-A2"
WRONG_PASSWORD = "ZzSenhaErradaSintetica99"
SELECT_SQL = """
SELECT
  nr_acesso,
  id_paciente,
  nome_paciente,
  nascimento,
  sexo,
  modalidade,
  ae_sala,
  descricao,
  data_exame,
  hora_exame,
  study_uid,
  situacao
FROM dbo.vw_agenda_sintetica
"""
MAPPING = {
    "accession_number": "nr_acesso",
    "patient_id": "id_paciente",
    "patient_name": "nome_paciente",
    "patient_birth_date": "nascimento",
    "patient_sex": "sexo",
    "modality": "modalidade",
    "station_aet": "ae_sala",
    "procedure_description": "descricao",
    "scheduled_date": "data_exame",
    "scheduled_time": "hora_exame",
    "study_instance_uid": "study_uid",
    "status": "situacao",
    "status_cancelled": "CANCELADO,CANCELADA",
    "status_performed": "REALIZADO,CONCLUIDO",
}


def _env_secret(name: str) -> str:
    current = os.environ.get(name, "").strip()
    if current:
        return current
    generated = "Aa1!" + secrets.token_hex(12)
    os.environ[name] = generated
    return generated


def _connect(server, port, user, password, database, login_timeout=5):
    import pymssql

    return pymssql.connect(
        server=server,
        port=int(port),
        user=user,
        password=password,
        database=database,
        login_timeout=login_timeout,
        timeout=30,
        charset="UTF-8",
    )


def _exec(conn, sql: str) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
    finally:
        cursor.close()


def _permission_denied(exc: BaseException) -> None:
    text = " ".join(str(exc).split()).lower()
    assert any(token in text for token in ("denied", "permission", "negad", "229", "262")), text[:160]


def _provision(server: dict) -> None:
    sa_password = server["sa_password"]
    ro_password = server["ro_password"]
    master = _connect(server["host"], server["port"], "sa", sa_password, "master")
    master.autocommit(True)
    try:
        _exec(master, f"IF DB_ID(N'{DATABASE}') IS NULL CREATE DATABASE {DATABASE}")
        login_password = "N'" + ro_password.replace("'", "''") + "'"
        _exec(
            master,
            f"""
            IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'{RO_USER}')
                CREATE LOGIN {RO_USER} WITH PASSWORD = {login_password},
                    CHECK_POLICY = ON, CHECK_EXPIRATION = OFF;
            ELSE
                ALTER LOGIN {RO_USER} WITH PASSWORD = {login_password},
                    CHECK_POLICY = ON, CHECK_EXPIRATION = OFF;
            """,
        )
    finally:
        master.close()

    db = _connect(server["host"], server["port"], "sa", sa_password, DATABASE)
    db.autocommit(True)
    try:
        _exec(
            db,
            """
            IF OBJECT_ID(N'dbo.agenda_sintetica', N'U') IS NULL
            CREATE TABLE dbo.agenda_sintetica (
                nr_acesso NVARCHAR(32) NULL,
                id_paciente NVARCHAR(64) NULL,
                nome_paciente NVARCHAR(128) NULL,
                nascimento DATE NULL,
                sexo NVARCHAR(16) NULL,
                modalidade NVARCHAR(16) NULL,
                ae_sala NVARCHAR(16) NULL,
                descricao NVARCHAR(128) NULL,
                data_exame DATE NULL,
                hora_exame TIME NULL,
                study_uid NVARCHAR(64) NULL,
                situacao NVARCHAR(32) NULL
            )
            """,
        )
        _exec(
            db,
            """
            CREATE OR ALTER VIEW dbo.vw_agenda_sintetica AS
            SELECT nr_acesso, id_paciente, nome_paciente, nascimento, sexo,
                   modalidade, ae_sala, descricao, data_exame, hora_exame,
                   study_uid, situacao
            FROM dbo.agenda_sintetica
            """,
        )
        _exec(
            db,
            f"""
            IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'{RO_USER}')
                CREATE USER {RO_USER} FOR LOGIN {RO_USER};
            GRANT SELECT ON dbo.vw_agenda_sintetica TO {RO_USER};
            DENY INSERT, UPDATE, DELETE ON dbo.agenda_sintetica TO {RO_USER};
            DENY INSERT, UPDATE, DELETE ON dbo.vw_agenda_sintetica TO {RO_USER};
            """,
        )
    finally:
        db.close()


def _wait_ready(server: dict) -> None:
    deadline = time.time() + 180
    last = "ainda não respondeu"
    while time.time() < deadline:
        try:
            conn = _connect(server["host"], server["port"], "sa", server["sa_password"], "master", login_timeout=3)
            conn.close()
            return
        except Exception as exc:
            last = type(exc).__name__
            time.sleep(3)
    raise RuntimeError(f"SQL Server sintético não ficou pronto ({last})")


def _start_container(port: int) -> None:
    if subprocess.run(["docker", "inspect", CONTAINER], capture_output=True).returncode == 0:
        subprocess.run(["docker", "rm", "-f", CONTAINER], check=False, capture_output=True)
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            CONTAINER,
            "-e",
            "ACCEPT_EULA=Y",
            "-e",
            "MSSQL_PID=Developer",
            "-e",
            "MSSQL_SA_PASSWORD",
            "-p",
            f"{port}:1433",
            "mcr.microsoft.com/mssql/server:2022-latest",
        ],
        check=True,
        env=os.environ,
    )


@pytest.fixture(scope="session")
def mssql_server():
    host = os.environ.get("LEX_MWL_MSSQL_HOST", "").strip()
    started = False
    if host:
        port = int(os.environ.get("LEX_MWL_MSSQL_PORT", "1433"))
    else:
        if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
            pytest.fail("Docker é necessário para o SQL Server sintético, ou defina LEX_MWL_MSSQL_HOST.")
        host = "127.0.0.1"
        port = int(os.environ.get("LEX_MWL_MSSQL_PORT", "14333"))
        _env_secret("MSSQL_SA_PASSWORD")
        _start_container(port)
        started = True
    server = {
        "host": host,
        "port": port,
        "sa_password": _env_secret("MSSQL_SA_PASSWORD"),
        "ro_password": _env_secret("LEX_MWL_SQL_PASSWORD"),
    }
    try:
        _wait_ready(server)
        _provision(server)
    except Exception:
        if started:
            subprocess.run(["docker", "rm", "-f", CONTAINER], check=False, capture_output=True)
        raise
    yield server
    if started:
        subprocess.run(["docker", "rm", "-f", CONTAINER], check=False, capture_output=True)


@pytest.fixture
def agenda(mssql_server, tmp_path, monkeypatch):
    config = tmp_path / "orthanc.json"
    config.write_text("{}\n", encoding="utf-8")
    wl = tmp_path / "worklists"
    wl.mkdir()
    monkeypatch.setattr(settings, "orthanc_config_path", str(config))
    monkeypatch.setattr(settings, "orthanc_worklist_path", str(wl))
    monkeypatch.setenv("LEX_MWL_SQL_PASSWORD", mssql_server["ro_password"])
    monkeypatch.delenv("MSSQL_SA_PASSWORD", raising=False)

    async def _plugin_off():
        return False

    monkeypatch.setattr("app.admin.orthanc_mwl_plugin_enabled", _plugin_off)

    conn = _connect(
        mssql_server["host"],
        mssql_server["port"],
        "sa",
        mssql_server["sa_password"],
        DATABASE,
    )
    cursor = conn.cursor()
    cursor.execute("DELETE FROM dbo.agenda_sintetica")
    conn.commit()

    def insert(rows: list[dict]) -> None:
        for row in rows:
            cursor.execute(
                """
                INSERT INTO dbo.agenda_sintetica (
                    nr_acesso, id_paciente, nome_paciente, nascimento, sexo,
                    modalidade, ae_sala, descricao, data_exame, hora_exame,
                    study_uid, situacao
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    row.get("nr_acesso"),
                    row.get("id_paciente"),
                    row.get("nome_paciente"),
                    row.get("nascimento"),
                    row.get("sexo"),
                    row.get("modalidade"),
                    row.get("ae_sala"),
                    row.get("descricao"),
                    row.get("data_exame"),
                    row.get("hora_exame"),
                    row.get("study_uid"),
                    row.get("situacao"),
                ),
            )
        conn.commit()

    def configure(**overrides) -> None:
        payload = {
            "enabled": True,
            "driver": "mssql",
            "mode": "custom",
            "host": mssql_server["host"],
            "port": mssql_server["port"],
            "database": DATABASE,
            "username": RO_USER,
            "password_env": "LEX_MWL_SQL_PASSWORD",
            "table": "vw_agenda_sintetica",
            "custom_sql": SELECT_SQL,
            "field_mapping": dict(MAPPING),
            "modality_filter": [],
            "modality_routes": [],
            "sync_interval_minutes": 5,
            "schedule_window_days": 7,
            "schedule_timezone": "UTC",
            "login_timeout_seconds": 5,
            "query_timeout_seconds": 30,
        }
        payload.update(overrides)
        save_mwl_sql_config(payload)

    configure()
    today = datetime.now(timezone.utc).date()
    yield {
        "server": mssql_server,
        "insert": insert,
        "configure": configure,
        "worklists": wl,
        "today": today,
        "settings_file": tmp_path / "lex-pacs-settings.json",
    }
    cursor.close()
    conn.close()


def _exam(today, **overrides):
    row = {
        "nr_acesso": "SINT-A2-001",
        "id_paciente": PATIENT_ID,
        "nome_paciente": PATIENT,
        "nascimento": datetime(1980, 1, 15).date(),
        "sexo": "M",
        "modalidade": "DX",
        "ae_sala": "RX_SALA1",
        "descricao": "Tórax sintético",
        "data_exame": today,
        "hora_exame": "14:30:00",
        "study_uid": "1.2.826.0.1.3680043.8.498.7001001",
        "situacao": "AGENDADO",
    }
    row.update(overrides)
    return row


def _files(directory):
    return sorted(path.name for path in directory.glob("lex-*.wl"))


def _snapshot(directory):
    return {path.name: path.read_bytes() for path in directory.glob("lex-*.wl")}


def _assert_clean(text: str, *secrets: str) -> None:
    for marker in (PATIENT, PATIENT_ID, "JOÃO", "CONCEIÇÃO", "ÁVILA", "Tórax", "1980-01-15", "19800115", *secrets):
        assert marker not in text


def test_a1_usuario_so_leitura_nao_insere_nem_atualiza(agenda):
    server = agenda["server"]
    agenda["insert"]([_exam(agenda["today"])])
    ro = _connect(server["host"], server["port"], RO_USER, server["ro_password"], DATABASE)
    try:
        cursor = ro.cursor()
        cursor.execute("SELECT nr_acesso FROM dbo.vw_agenda_sintetica")
        found = [row[0] for row in cursor.fetchall()]
        assert found == ["SINT-A2-001"]
        with pytest.raises(Exception) as inserted:
            cursor.execute(
                "INSERT INTO dbo.agenda_sintetica (nr_acesso, situacao) VALUES (%s, %s)",
                ("SINT-NAO-GRAVAR", "AGENDADO"),
            )
            ro.commit()
        _permission_denied(inserted.value)
        with pytest.raises(Exception) as updated:
            cursor.execute("UPDATE dbo.vw_agenda_sintetica SET situacao = %s", ("REALIZADO",))
            ro.commit()
        _permission_denied(updated.value)
    finally:
        ro.close()

    result = run_mwl_sync("teste")
    assert result["read"] == 1
    assert result["synced"] == 1
    assert result["errors"] == 0
    assert _files(agenda["worklists"]) == ["lex-SINT-A2-001.wl"]


def test_a2_wl_com_acento_e_status_sem_paciente(agenda, client, caplog):
    import logging

    import pydicom

    agenda["insert"](
        [
            _exam(agenda["today"]),
            _exam(
                agenda["today"],
                nr_acesso="SINT-A2-SEM-UID",
                study_uid=None,
                nome_paciente="ZZSINT^MARIA ÁVILA",
                id_paciente="SINT-PID-A2B",
                sexo="FEMININO",
            ),
        ]
    )
    caplog.set_level(logging.INFO)
    result = run_mwl_sync("teste")
    assert result["read"] == 2
    assert result["synced"] == 2
    assert result["errors"] == 0
    assert _files(agenda["worklists"]) == ["lex-SINT-A2-001.wl", "lex-SINT-A2-SEM-UID.wl"]

    path = agenda["worklists"] / "lex-SINT-A2-001.wl"
    raw = path.read_bytes()
    assert "JOÃO".encode("utf-8") in raw
    assert "CONCEIÇÃO".encode("utf-8") in raw
    ds = pydicom.dcmread(path)
    assert "ISO_IR 192" in str(ds.SpecificCharacterSet)
    assert "JOÃO" in str(ds.PatientName)
    assert str(ds.PatientID) == PATIENT_ID
    assert str(ds.PatientBirthDate) == "19800115"
    assert str(ds.PatientSex) == "M"
    assert str(ds.AccessionNumber) == "SINT-A2-001"
    assert str(ds.StudyInstanceUID) == "1.2.826.0.1.3680043.8.498.7001001"
    assert "Tórax" in str(ds.RequestedProcedureDescription)
    sps = ds.ScheduledProcedureStepSequence[0]
    assert str(sps.Modality) == "DX"
    assert str(sps.ScheduledStationAETitle) == "RX_SALA1"
    assert str(sps.ScheduledProcedureStepStartDate) == agenda["today"].strftime("%Y%m%d")
    assert "143000" in "".join(ch for ch in str(sps.ScheduledProcedureStepStartTime) if ch.isdigit())

    other = pydicom.dcmread(agenda["worklists"] / "lex-SINT-A2-SEM-UID.wl")
    assert str(other.PatientSex) == "F"
    assert str(other.StudyInstanceUID).startswith("2.25.")
    uid = str(other.StudyInstanceUID)
    run_mwl_sync("teste")
    again = pydicom.dcmread(agenda["worklists"] / "lex-SINT-A2-SEM-UID.wl")
    assert str(again.StudyInstanceUID) == uid
    assert _files(agenda["worklists"]) == ["lex-SINT-A2-001.wl", "lex-SINT-A2-SEM-UID.wl"]

    meta = get_mwl_sync_meta()
    assert meta["last_read"] == 2
    assert meta["last_written"] == 2
    assert meta["last_errors"] == 0
    assert meta["last_at"]
    _assert_clean(meta["last_error"], agenda["server"]["ro_password"], agenda["server"]["sa_password"])
    _assert_clean(caplog.text, agenda["server"]["ro_password"], agenda["server"]["sa_password"])
    _assert_clean(agenda["settings_file"].read_text(encoding="utf-8"), agenda["server"]["ro_password"])

    login = client.post(
        "/api/auth/clinical/login",
        json={"username": "admin", "password": "Senha-Inicial-123"},
    )
    assert login.status_code == 200, login.text
    changed = client.post(
        "/api/auth/clinical/change-password",
        json={"current_password": "Senha-Inicial-123", "new_password": "Nova-Senha-Admin-456"},
    )
    assert changed.status_code == 200, changed.text
    status = client.get("/api/admin/pacs/mwl/status")
    assert status.status_code == 200, status.text
    sync = status.json()["sync"]
    assert sync["last_read"] == 2
    assert sync["last_written"] == 2
    assert sync["last_removed"] == 0
    assert sync["last_errors"] == 0
    assert sync["last_at"]
    _assert_clean(status.text, agenda["server"]["ro_password"], agenda["server"]["sa_password"])


def test_a4_remove_cancelado_realizado_e_fora_da_janela(agenda):
    """Janela de 7 dias no teste: hoje até D+6 inclusive. D+7 e além ficam de fora."""
    today = agenda["today"]
    agenda["insert"](
        [
            _exam(today, nr_acesso="SINT-HOJE", situacao="AGENDADO"),
            _exam(today + timedelta(days=6), nr_acesso="SINT-D6", situacao="AGENDADO"),
            _exam(today + timedelta(days=7), nr_acesso="SINT-D7", situacao="AGENDADO"),
            _exam(today + timedelta(days=8), nr_acesso="SINT-DEPOIS", situacao="AGENDADO"),
            _exam(today - timedelta(days=1), nr_acesso="SINT-ONTEM", situacao="AGENDADO"),
            _exam(today, nr_acesso="SINT-CANCEL", situacao="CANCELADA"),
            _exam(today, nr_acesso="SINT-FEITO", situacao="CONCLUIDO"),
        ]
    )
    result = run_mwl_sync("teste")
    assert result["read"] == 7
    assert result["errors"] == 0
    assert result["synced"] == 2
    assert _files(agenda["worklists"]) == ["lex-SINT-D6.wl", "lex-SINT-HOJE.wl"]

    agenda["configure"](schedule_window_days=1)
    narrowed = run_mwl_sync("teste")
    assert narrowed["removed"] >= 1
    assert _files(agenda["worklists"]) == ["lex-SINT-HOJE.wl"]
    meta = get_mwl_sync_meta()
    assert meta["last_removed"] >= 1
    _assert_clean(meta["last_error"])


def test_a6_accession_duplicado_e_campo_nulo(agenda, caplog):
    import logging

    today = agenda["today"]
    agenda["insert"](
        [
            _exam(today, nr_acesso="SINT-DUP", descricao="Primeira"),
            _exam(today, nr_acesso="SINT-DUP", descricao="Segunda"),
            _exam(today, nr_acesso=None, situacao="AGENDADO"),
            _exam(today, nr_acesso="SINT-SEM-NOME", nome_paciente=None),
            _exam(today, nr_acesso="SINT-SEM-NASC", nascimento=None),
            _exam(today, nr_acesso="", situacao="AGENDADO"),
        ]
    )
    caplog.set_level(logging.INFO)
    result = run_mwl_sync("teste")
    assert result["read"] == 6
    assert result["errors"] == 4
    assert result["synced"] == 1
    assert _files(agenda["worklists"]) == ["lex-SINT-DUP.wl"]
    meta = get_mwl_sync_meta()
    assert meta["last_errors"] == 4
    assert meta["last_read"] == 6
    assert meta["last_written"] == 1
    _assert_clean(meta["last_error"], agenda["server"]["ro_password"])
    _assert_clean(caplog.text, agenda["server"]["ro_password"])


def _fail_and_keep(agenda, caplog, **config):
    import logging

    before = _snapshot(agenda["worklists"])
    assert before
    agenda["configure"](**config)
    caplog.set_level(logging.WARNING)
    with pytest.raises(HTTPException) as raised:
        run_mwl_sync("teste")
    assert _snapshot(agenda["worklists"]) == before
    meta = get_mwl_sync_meta()
    assert meta["last_removed"] == 0
    assert meta["last_written"] == 0
    assert meta["last_errors"] == 1
    assert meta["last_error"]
    secrets = (agenda["server"]["ro_password"], agenda["server"]["sa_password"], WRONG_PASSWORD)
    _assert_clean(meta["last_error"], *secrets)
    _assert_clean(str(raised.value.detail), *secrets)
    _assert_clean(caplog.text, *secrets)
    caplog.clear()


def test_a5_origem_fora_timeout_senha_errada_e_retry(agenda, caplog):
    agenda["insert"]([_exam(agenda["today"])])
    first = run_mwl_sync("teste")
    assert first["synced"] == 1

    _fail_and_keep(agenda, caplog, host="127.0.0.1", port=1, login_timeout_seconds=2)
    # 192.0.2.1 é a rede de documentação (não roteia). O login_timeout encerra a tentativa.
    _fail_and_keep(
        agenda,
        caplog,
        host="192.0.2.1",
        port=1433,
        login_timeout_seconds=2,
        query_timeout_seconds=2,
    )

    monkey_password = os.environ["LEX_MWL_SQL_PASSWORD"]
    os.environ["LEX_MWL_SQL_PASSWORD"] = WRONG_PASSWORD
    try:
        _fail_and_keep(
            agenda,
            caplog,
            host=agenda["server"]["host"],
            port=agenda["server"]["port"],
            login_timeout_seconds=5,
        )
    finally:
        os.environ["LEX_MWL_SQL_PASSWORD"] = monkey_password

    agenda["configure"](
        host=agenda["server"]["host"],
        port=agenda["server"]["port"],
        login_timeout_seconds=5,
    )
    retried = run_mwl_sync("teste")
    assert retried["synced"] == 1
    assert retried["errors"] == 0
    assert _files(agenda["worklists"]) == ["lex-SINT-A2-001.wl"]
    assert get_mwl_sync_meta()["last_error"] == ""
