from __future__ import annotations

from typing import Any

DRIVER_REGISTRY: dict[str, dict[str, Any]] = {
    "postgresql": {
        "id": "postgresql",
        "label": "PostgreSQL",
        "default_port": 5432,
        "package": "psycopg2",
    },
    "mysql": {
        "id": "mysql",
        "label": "MySQL / MariaDB",
        "default_port": 3306,
        "package": "pymysql",
    },
    "mssql": {
        "id": "mssql",
        "label": "Microsoft SQL Server",
        "default_port": 1433,
        "package": "pymssql",
    },
    "oracle": {
        "id": "oracle",
        "label": "Oracle Database",
        "default_port": 1521,
        "package": "oracledb",
    },
}

MWL_FIELDS = [
    "accession_number",
    "patient_id",
    "patient_name",
    "modality",
    "station_aet",
    "procedure_description",
    "scheduled_date",
]

DEFAULT_FIELD_MAPPING = {field: field for field in MWL_FIELDS}

DEFAULT_CUSTOM_SQL = """SELECT
  accession_number,
  patient_id,
  patient_name,
  modality,
  station_aet,
  procedure_description,
  scheduled_date
FROM lex_mwl_schedule
WHERE scheduled_date >= CURRENT_DATE - INTERVAL '1 day'
"""


def list_drivers() -> list[dict[str, Any]]:
    return [
        {
            "id": meta["id"],
            "label": meta["label"],
            "default_port": meta["default_port"],
        }
        for meta in DRIVER_REGISTRY.values()
    ]


def default_port(driver: str) -> int:
    meta = DRIVER_REGISTRY.get(driver) or DRIVER_REGISTRY["postgresql"]
    return int(meta["default_port"])
