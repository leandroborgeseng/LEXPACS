from __future__ import annotations

from datetime import date, datetime
from typing import Any

import psycopg2
from fastapi import HTTPException, status
from psycopg2.extras import RealDictCursor

from .mwl_sql import postgres_connection_params

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS lex_mwl_schedule (
    id SERIAL PRIMARY KEY,
    accession_number VARCHAR(32) NOT NULL UNIQUE,
    patient_id VARCHAR(64) NOT NULL,
    patient_name VARCHAR(128) NOT NULL,
    modality VARCHAR(16) NOT NULL,
    station_aet VARCHAR(16) NOT NULL,
    procedure_description VARCHAR(128) NOT NULL DEFAULT '',
    scheduled_date DATE NOT NULL DEFAULT CURRENT_DATE
);
"""

SEED_SQL = """
INSERT INTO lex_mwl_schedule (
    accession_number, patient_id, patient_name, modality,
    station_aet, procedure_description, scheduled_date
) VALUES
    ('LEXMWL001', 'MWLTEST01', 'Paciente^MWL Teste', 'DX', 'RX_SALA1', 'Raio-X sala 1', CURRENT_DATE),
    ('LEXMWL002', 'MWLTEST02', 'Paciente^MWL CT', 'CT', 'CT_SALA1', 'Tomografia', CURRENT_DATE)
ON CONFLICT (accession_number) DO NOTHING
"""


def _connect() -> psycopg2.extensions.connection:
    params = postgres_connection_params()
    params.pop("table", None)
    return psycopg2.connect(**params)


def _table_name() -> str:
    return postgres_connection_params()["table"]


def ensure_mwl_schema(conn: psycopg2.extensions.connection, *, seed_demo: bool = True) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
        if seed_demo:
            cur.execute(SEED_SQL)
    conn.commit()


def fetch_mwl_rows(*, include_yesterday: bool = True) -> list[dict[str, Any]]:
    table = _table_name()
    conn = _connect()
    try:
        ensure_mwl_schema(conn)
        date_filter = "scheduled_date >= CURRENT_DATE - INTERVAL '1 day'" if include_yesterday else "TRUE"
        query = f"""
            SELECT accession_number, patient_id, patient_name, modality,
                   station_aet, procedure_description, scheduled_date
            FROM {table}
            WHERE {date_filter}
            ORDER BY scheduled_date, accession_number
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query)
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def upsert_mwl_row(row: dict[str, Any]) -> None:
    table = _table_name()
    accession = str(row.get("accession_number", "")).strip()
    if not accession:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Accession number obrigatório.")
    scheduled = row.get("scheduled_date")
    if isinstance(scheduled, str):
        scheduled = scheduled.strip()[:10]
        if len(scheduled) == 8 and scheduled.isdigit():
            scheduled = f"{scheduled[:4]}-{scheduled[4:6]}-{scheduled[6:8]}"
    elif isinstance(scheduled, datetime):
        scheduled = scheduled.date()
    elif not isinstance(scheduled, date):
        scheduled = date.today()

    payload = {
        "accession_number": accession[:32],
        "patient_id": str(row.get("patient_id", "")).strip()[:64] or "UNKNOWN",
        "patient_name": str(row.get("patient_name", "")).strip()[:128] or "UNKNOWN",
        "modality": str(row.get("modality", "")).strip().upper()[:16] or "OT",
        "station_aet": str(row.get("station_aet", "")).strip().upper()[:16] or "UNKNOWN",
        "procedure_description": str(row.get("procedure_description", "")).strip()[:128],
        "scheduled_date": scheduled,
    }

    conn = _connect()
    try:
        ensure_mwl_schema(conn, seed_demo=False)
        query = f"""
            INSERT INTO {table} (
                accession_number, patient_id, patient_name, modality,
                station_aet, procedure_description, scheduled_date
            ) VALUES (
                %(accession_number)s, %(patient_id)s, %(patient_name)s, %(modality)s,
                %(station_aet)s, %(procedure_description)s, %(scheduled_date)s
            )
            ON CONFLICT (accession_number) DO UPDATE SET
                patient_id = EXCLUDED.patient_id,
                patient_name = EXCLUDED.patient_name,
                modality = EXCLUDED.modality,
                station_aet = EXCLUDED.station_aet,
                procedure_description = EXCLUDED.procedure_description,
                scheduled_date = EXCLUDED.scheduled_date
        """
        with conn.cursor() as cur:
            cur.execute(query, payload)
        conn.commit()
    finally:
        conn.close()


def delete_mwl_row(accession_number: str) -> bool:
    table = _table_name()
    accession = accession_number.strip()
    if not accession:
        return False
    conn = _connect()
    try:
        ensure_mwl_schema(conn, seed_demo=False)
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {table} WHERE accession_number = %s", (accession,))
            deleted = cur.rowcount > 0
        conn.commit()
        return deleted
    finally:
        conn.close()
