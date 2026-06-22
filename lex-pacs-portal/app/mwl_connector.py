from __future__ import annotations

import os
import re
from typing import Any

from fastapi import HTTPException, status

from .mwl_drivers import DRIVER_REGISTRY, default_port

_FORBIDDEN_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|MERGE|EXEC|EXECUTE|CALL)\b",
    re.IGNORECASE,
)


def validate_select_sql(sql: str) -> str:
    text = sql.strip().rstrip(";")
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SQL vazio.")
    if _FORBIDDEN_SQL.search(text):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas consultas SELECT são permitidas.",
        )
    if not text.lstrip().upper().startswith("SELECT"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A consulta deve começar com SELECT.",
        )
    return text


def _password_from_env(env_name: str) -> str:
    password = os.environ.get(env_name, "")
    if not password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Senha SQL não configurada (env {env_name}).",
        )
    return password


def connect(cfg: dict[str, Any]):
    driver = str(cfg.get("driver") or "postgresql")
    if driver not in DRIVER_REGISTRY:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Driver SQL não suportado.")

    host = str(cfg.get("host") or "").strip()
    if not host:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Host SQL obrigatório.")

    port = int(cfg.get("port") or default_port(driver))
    database = str(cfg.get("database") or "").strip()
    username = str(cfg.get("username") or "").strip()
    password_env = str(cfg.get("password_env") or "POSTGRES_PASSWORD")
    password = _password_from_env(password_env)

    if driver == "postgresql":
        import psycopg2

        return psycopg2.connect(
            host=host,
            port=port,
            dbname=database or "orthanc",
            user=username,
            password=password,
        )

    if driver == "mysql":
        import pymysql

        return pymysql.connect(
            host=host,
            port=port,
            database=database,
            user=username,
            password=password,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=30,
            read_timeout=120,
        )

    if driver == "mssql":
        import pymssql

        return pymssql.connect(
            server=host,
            port=port,
            user=username,
            password=password,
            database=database,
            login_timeout=30,
            timeout=120,
        )

    if driver == "oracle":
        import oracledb

        service = database or "ORCL"
        dsn = oracledb.makedsn(host, port, service_name=service)
        return oracledb.connect(user=username, password=password, dsn=dsn)

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Driver SQL não suportado.")


def _rows_as_dicts(cursor, driver: str, rows: list) -> list[dict[str, Any]]:
    if driver == "mysql":
        return [dict(row) for row in rows]
    columns = [str(col[0]) for col in (cursor.description or [])]
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append({columns[i]: row[i] for i in range(len(columns))})
    return result


def execute_select(cfg: dict[str, Any], sql: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    driver = str(cfg.get("driver") or "postgresql")
    query = validate_select_sql(sql)
    conn = connect(cfg)
    try:
        if driver == "mysql":
            with conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchmany(limit) if limit else cur.fetchall()
                return [dict(row) for row in rows]

        cur = conn.cursor()
        try:
            cur.execute(query)
            rows = cur.fetchmany(limit) if limit else cur.fetchall()
            return _rows_as_dicts(cur, driver, rows)
        finally:
            cur.close()
    finally:
        conn.close()


def test_connection(cfg: dict[str, Any]) -> dict[str, Any]:
    driver = str(cfg.get("driver") or "postgresql")
    conn = connect(cfg)
    try:
        if driver == "postgresql":
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        elif driver == "mysql":
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        elif driver == "mssql":
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
        elif driver == "oracle":
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM DUAL")
        return {"ok": True, "driver": driver}
    finally:
        conn.close()
