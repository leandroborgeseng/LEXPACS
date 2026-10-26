"""Usuários locais do LEX PACS (substitui Keycloak/htpasswd).

- Armazenamento SQLite (LOCAL_USERS_DB_PATH), hash Argon2id (argon2-cffi).
- Perfis: admin, medico, tecnico, recepcao, paciente.
- Bloqueio após N falhas (padrão 5) por M minutos (padrão 15).
- Sessões no servidor com expiração por inatividade (padrão 30 min).
- Admin inicial por env (LEX_ADMIN_USER / LEX_ADMIN_PASSWORD), troca obrigatória no 1º acesso.
"""
from __future__ import annotations

import re
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from .config import settings

PROFILES = ("admin", "medico", "tecnico", "recepcao", "paciente")
INTERNAL_PROFILES = ("admin", "medico", "tecnico", "recepcao")
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")

_hasher = PasswordHasher()
_lock = threading.Lock()
# Hash fixo usado para equalizar o tempo quando o usuário não existe.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


class UserError(ValueError):
    """Erro de validação (mensagem segura para o cliente)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _db_path() -> Path:
    return Path(settings.local_users_db_path)


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                full_name TEXT NOT NULL DEFAULT '',
                profile TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                must_change_password INTEGER NOT NULL DEFAULT 1,
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT,
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                sid TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_seen TEXT NOT NULL
            );
            """
        )


def validate_password(password: str) -> None:
    if len(password or "") < settings.password_min_length:
        raise UserError(f"A senha precisa ter pelo menos {settings.password_min_length} caracteres.")
    if len(password) > 256:
        raise UserError("Senha longa demais.")


def validate_username(username: str) -> str:
    username = (username or "").strip().lower()
    if not USERNAME_RE.match(username):
        raise UserError("Usuário inválido: use 3 a 64 caracteres (a-z, 0-9, . _ -).")
    return username


def _public(row: sqlite3.Row) -> dict[str, Any]:
    locked_until = _parse(row["locked_until"])
    return {
        "username": row["username"],
        "full_name": row["full_name"],
        "profile": row["profile"],
        "active": bool(row["active"]),
        "must_change_password": bool(row["must_change_password"]),
        "locked": bool(locked_until and locked_until > _now()),
        "created_at": row["created_at"],
        "created_by": row["created_by"],
        "updated_at": row["updated_at"],
    }


def get_user(username: str) -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username.strip().lower(),)).fetchone()
    return _public(row) if row else None


def list_users() -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY username").fetchall()
    return [_public(r) for r in rows]


def count_users() -> int:
    with _conn() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])


def create_user(
    username: str,
    password: str,
    profile: str,
    *,
    full_name: str = "",
    created_by: str = "",
    must_change_password: bool = True,
    allow_patient: bool = False,
) -> dict[str, Any]:
    username = validate_username(username)
    allowed = PROFILES if allow_patient else INTERNAL_PROFILES
    if profile not in allowed:
        raise UserError(f"Perfil inválido. Use: {', '.join(allowed)}.")
    validate_password(password)
    now = _iso(_now())
    with _conn() as conn:
        exists = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
        if exists:
            raise UserError("Usuário já existe.")
        conn.execute(
            """INSERT INTO users (username, full_name, profile, password_hash, active,
                   must_change_password, failed_attempts, created_at, created_by, updated_at)
               VALUES (?, ?, ?, ?, 1, ?, 0, ?, ?, ?)""",
            (username, full_name.strip()[:128], profile, _hasher.hash(password),
             1 if must_change_password else 0, now, created_by, now),
        )
    return get_user(username)  # type: ignore[return-value]


def set_active(username: str, active: bool) -> dict[str, Any]:
    username = username.strip().lower()
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE users SET active = ?, updated_at = ? WHERE username = ?",
            (1 if active else 0, _iso(_now()), username),
        )
        if cur.rowcount == 0:
            raise UserError("Usuário não encontrado.")
        if not active:
            conn.execute("DELETE FROM sessions WHERE username = ?", (username,))
    return get_user(username)  # type: ignore[return-value]


def admin_reset_password(username: str, new_password: str) -> dict[str, Any]:
    validate_password(new_password)
    username = username.strip().lower()
    with _conn() as conn:
        cur = conn.execute(
            """UPDATE users SET password_hash = ?, must_change_password = 1, failed_attempts = 0,
                   locked_until = NULL, updated_at = ? WHERE username = ?""",
            (_hasher.hash(new_password), _iso(_now()), username),
        )
        if cur.rowcount == 0:
            raise UserError("Usuário não encontrado.")
        conn.execute("DELETE FROM sessions WHERE username = ?", (username,))
    return get_user(username)  # type: ignore[return-value]


def change_password(username: str, current_password: str, new_password: str) -> None:
    username = username.strip().lower()
    validate_password(new_password)
    if current_password == new_password:
        raise UserError("A nova senha deve ser diferente da atual.")
    with _conn() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE username = ? AND active = 1", (username,)).fetchone()
        if not row:
            raise UserError("Usuário não encontrado.")
        try:
            _hasher.verify(row["password_hash"], current_password)
        except (VerifyMismatchError, VerificationError, InvalidHashError) as exc:
            raise UserError("Senha atual incorreta.") from exc
        conn.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 0, updated_at = ? WHERE username = ?",
            (_hasher.hash(new_password), _iso(_now()), username),
        )


class AuthResult:
    def __init__(self, ok: bool, reason: str = "", user: dict[str, Any] | None = None):
        self.ok = ok
        self.reason = reason  # invalid | locked | inactive
        self.user = user


def verify_login(username: str, password: str) -> AuthResult:
    username = (username or "").strip().lower()
    now = _now()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not row:
            try:
                _hasher.verify(_DUMMY_HASH, password or "x")
            except VerificationError:
                pass
            return AuthResult(False, "invalid")
        locked_until = _parse(row["locked_until"])
        if locked_until and locked_until > now:
            return AuthResult(False, "locked")
        if not row["active"]:
            return AuthResult(False, "inactive")
        try:
            _hasher.verify(row["password_hash"], password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            attempts = int(row["failed_attempts"] or 0) + 1
            locked = None
            if attempts >= settings.login_max_failures:
                locked = _iso(now + timedelta(minutes=settings.login_lockout_minutes))
                attempts = 0
            conn.execute(
                "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE username = ?",
                (attempts, locked, username),
            )
            return AuthResult(False, "locked" if locked else "invalid")
        new_hash = None
        if _hasher.check_needs_rehash(row["password_hash"]):
            new_hash = _hasher.hash(password)
        conn.execute(
            "UPDATE users SET failed_attempts = 0, locked_until = NULL"
            + (", password_hash = ?" if new_hash else "")
            + " WHERE username = ?",
            ((new_hash, username) if new_hash else (username,)),
        )
    return AuthResult(True, user=get_user(username))


# ── Sessões (inatividade) ──

def create_session(username: str) -> str:
    sid = secrets.token_urlsafe(32)
    now = _iso(_now())
    with _conn() as conn:
        conn.execute(
            "INSERT INTO sessions (sid, username, created_at, last_seen) VALUES (?, ?, ?, ?)",
            (sid, username.strip().lower(), now, now),
        )
    return sid


def touch_session(sid: str) -> dict[str, Any] | None:
    """Valida a sessão (inatividade + usuário ativo) e renova last_seen."""
    if not sid:
        return None
    now = _now()
    idle = timedelta(minutes=settings.session_idle_minutes)
    with _conn() as conn:
        row = conn.execute(
            """SELECT s.sid, s.last_seen, u.* FROM sessions s JOIN users u ON u.username = s.username
               WHERE s.sid = ?""",
            (sid,),
        ).fetchone()
        if not row:
            return None
        last_seen = _parse(row["last_seen"])
        if not row["active"] or not last_seen or now - last_seen > idle:
            conn.execute("DELETE FROM sessions WHERE sid = ?", (sid,))
            return None
        conn.execute("UPDATE sessions SET last_seen = ? WHERE sid = ?", (_iso(now), sid))
    return _public(row)


def delete_session(sid: str) -> None:
    if not sid:
        return
    with _conn() as conn:
        conn.execute("DELETE FROM sessions WHERE sid = ?", (sid,))


def bootstrap_admin() -> bool:
    """Cria o admin inicial a partir do env se ainda não houver usuários."""
    user = (settings.lex_admin_user or "").strip()
    password = settings.lex_admin_password or ""
    init_db()
    if not user or not password or count_users() > 0:
        return False
    create_user(user, password, "admin", full_name="Administrador", created_by="bootstrap",
                must_change_password=True)
    return True
