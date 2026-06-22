from __future__ import annotations

import logging
import socket
import threading
from typing import Callable

from .hl7_orm import process_mllp_frame
from .hl7_settings import get_hl7_config

logger = logging.getLogger("lex_pacs.hl7_mllp")

_server_thread: threading.Thread | None = None
_stop_event = threading.Event()


def _handle_client(conn: socket.socket, addr: tuple[str, int]) -> None:
    chunks: list[bytes] = []
    try:
        conn.settimeout(30.0)
        while True:
            data = conn.recv(65536)
            if not data:
                break
            chunks.append(data)
            if b"\x1c" in data:
                break
        if not chunks:
            return
        frame = b"".join(chunks)
        response = process_mllp_frame(frame, actor=f"hl7:{addr[0]}")
        conn.sendall(response)
    except Exception as exc:
        logger.warning("HL7 MLLP cliente %s erro: %s", addr, exc)
    finally:
        try:
            conn.close()
        except OSError:
            pass


def _serve_forever(host: str, port: int) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(32)
    sock.settimeout(1.0)
    logger.info("HL7 MLLP escutando em %s:%s", host, port)
    while not _stop_event.is_set():
        try:
            conn, addr = sock.accept()
        except socket.timeout:
            continue
        except OSError as exc:
            if not _stop_event.is_set():
                logger.warning("HL7 accept falhou: %s", exc)
            break
        threading.Thread(target=_handle_client, args=(conn, addr), daemon=True).start()
    try:
        sock.close()
    except OSError:
        pass
    logger.info("HL7 MLLP encerrado")


def start_hl7_mllp_server() -> None:
    global _server_thread
    cfg = get_hl7_config()
    if not cfg.get("enabled", True):
        logger.info("HL7 ORM desabilitado (hl7_orm.enabled=false)")
        return
    if _server_thread and _server_thread.is_alive():
        return
    _stop_event.clear()
    host = str(cfg.get("listen_host", "0.0.0.0"))
    port = int(cfg.get("listen_port", 2575))

    def runner() -> None:
        try:
            _serve_forever(host, port)
        except OSError as exc:
            logger.error("HL7 MLLP não iniciou em %s:%s — %s", host, port, exc)

    _server_thread = threading.Thread(target=runner, name="hl7-mllp", daemon=True)
    _server_thread.start()


def stop_hl7_mllp_server() -> None:
    global _server_thread
    _stop_event.set()
    if _server_thread and _server_thread.is_alive():
        _server_thread.join(timeout=3.0)
    _server_thread = None


def restart_hl7_mllp_server() -> None:
    stop_hl7_mllp_server()
    _stop_event.clear()
    start_hl7_mllp_server()
