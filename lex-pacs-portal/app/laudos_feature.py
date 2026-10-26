"""LD1–LD5: liga/desliga laudos por LEX_LAUDOS_HABILITADO (padrão: desligado).

Desligado: toda rota de laudo responde 404 (clínica e paciente, qualquer método),
antes de autenticação, sem tocar nos arquivos de laudo (nada é apagado — LD3).
Ligado: rotas clínicas de laudo exigem can_draft ou can_sign (403 para os demais).
"""
from __future__ import annotations

import re

from fastapi import HTTPException, Request, status

from .clinical_auth import require_clinical_user
from .clinical_session import ClinicalUser, clinical_permissions
from .config import settings

# Caminhos internos do portal (o gateway reescreve /clinica-api/* e /paciente-api/* para /api/*).
# Comparação sem diferenciar maiúsculas e tolerante a barras repetidas/finais.
LAUDO_PATH_RE = re.compile(
    r"^/+api/+(?:reports(?:/|$)|studies/+[^/]+/+report(?:/|$))",
    re.IGNORECASE,
)


def laudos_habilitados() -> bool:
    return bool(settings.lex_laudos_habilitado)


def is_laudo_path(path: str) -> bool:
    return bool(LAUDO_PATH_RE.match(path or ""))


def pode_laudar(user: ClinicalUser) -> bool:
    perms = clinical_permissions(user)
    return bool(perms.get("can_draft") or perms.get("can_sign"))


def laudos_visiveis_para(user: ClinicalUser) -> bool:
    return laudos_habilitados() and pode_laudar(user)


def require_laudador(request: Request) -> ClinicalUser:
    """Dependência do router /api/reports (só relevante com a flag ligada)."""
    if not laudos_habilitados():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    user = require_clinical_user(request)
    if not pode_laudar(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Laudos restritos ao perfil laudador.")
    return user
