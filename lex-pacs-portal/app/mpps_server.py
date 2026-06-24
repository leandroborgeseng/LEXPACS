from __future__ import annotations

import logging
import threading
from typing import Any

from pynetdicom import AE, evt
from pynetdicom.sop_class import ModalityPerformedProcedureStep, Verification

from .mpps_service import on_mpps_create, on_mpps_set
from .mpps_settings import get_mpps_config

logger = logging.getLogger("lex_pacs.mpps_server")

_server = None
_server_thread: threading.Thread | None = None
_stop_event = threading.Event()


def _handle_echo(event: Any) -> int:
    return 0x0000


def _start_association_server(host: str, port: int, aet: str):
    ae = AE(ae_title=aet)
    ae.add_supported_context(ModalityPerformedProcedureStep)
    ae.add_supported_context(Verification)
    handlers = [
        (evt.EVT_N_CREATE, on_mpps_create),
        (evt.EVT_N_SET, on_mpps_set),
        (evt.EVT_C_ECHO, _handle_echo),
    ]
    return ae.start_server((host, port), block=False, evt_handlers=handlers)


def start_mpps_server() -> None:
    global _server, _server_thread
    cfg = get_mpps_config()
    if not cfg.get("enabled", True):
        logger.info("MPPS desabilitado (mpps.enabled=false)")
        return
    if _server_thread and _server_thread.is_alive():
        return

    _stop_event.clear()
    host = str(cfg.get("listen_host", "0.0.0.0"))
    port = int(cfg.get("listen_port", 4243))
    aet = str(cfg.get("aet", "LEXMPPS"))

    def runner() -> None:
        global _server
        try:
            _server = _start_association_server(host, port, aet)
            logger.info("MPPS SCP escutando em %s:%s (AET %s)", host, port, aet)
            while not _stop_event.is_set():
                _stop_event.wait(1.0)
        except OSError as exc:
            logger.error("MPPS SCP não iniciou em %s:%s — %s", host, port, exc)
        finally:
            if _server is not None:
                try:
                    _server.shutdown()
                except Exception:
                    pass
                _server = None
            logger.info("MPPS SCP encerrado")

    _server_thread = threading.Thread(target=runner, name="mpps-scp", daemon=True)
    _server_thread.start()


def stop_mpps_server() -> None:
    global _server, _server_thread
    _stop_event.set()
    if _server is not None:
        try:
            _server.shutdown()
        except Exception:
            pass
        _server = None
    if _server_thread and _server_thread.is_alive():
        _server_thread.join(timeout=5.0)
    _server_thread = None


def restart_mpps_server() -> None:
    stop_mpps_server()
    _stop_event.clear()
    start_mpps_server()


def mpps_server_running() -> bool:
    return _server is not None and _server_thread is not None and _server_thread.is_alive()
