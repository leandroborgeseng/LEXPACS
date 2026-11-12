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

# Colunas lidas da origem. `status` não vira tag DICOM: serve para cancelado/realizado.
MWL_COLUMN_FIELDS = [
    "accession_number",
    "patient_id",
    "patient_name",
    "patient_birth_date",
    "patient_sex",
    "modality",
    "station_aet",
    "procedure_description",
    "scheduled_date",
    "scheduled_time",
    "study_instance_uid",
    "status",
]

# Literais do mapeamento (não são nomes de coluna). A origem real ainda não é conhecida.
MWL_VALUE_DEFAULTS = {
    "status_cancelled": "CANCELADO",
    "status_performed": "REALIZADO",
}

MWL_FIELDS = list(MWL_COLUMN_FIELDS)

DEFAULT_FIELD_MAPPING = {field: field for field in MWL_COLUMN_FIELDS}
DEFAULT_FIELD_MAPPING.update(MWL_VALUE_DEFAULTS)

# A janela (padrão: 7 dias inclusive, hoje até D+6, fuso America/Sao_Paulo) e o
# status são aplicados na sincronização, não nesta consulta: a coluna e os
# valores reais da origem ainda não são conhecidos.
# A porta padrão do driver mssql é 1433 (conexão do cliente). Não publica porta.
DEFAULT_CUSTOM_SQL = """SELECT
  accession_number,
  patient_id,
  patient_name,
  patient_birth_date,
  patient_sex,
  modality,
  station_aet,
  procedure_description,
  scheduled_date,
  scheduled_time,
  study_instance_uid,
  status
FROM lex_mwl_schedule
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
