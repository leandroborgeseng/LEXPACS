from __future__ import annotations

import ipaddress
import logging
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from fastapi import HTTPException, status

from .config import settings
from .dicom_tls_settings import (
    get_dicom_tls_config,
    get_dicom_tls_stats,
    record_dicom_tls_generated,
    record_dicom_tls_test,
)
from .pacs_config import _read_config, _write_config

logger = logging.getLogger("lex_pacs.dicom_tls")

TLS_MODALITY_KEY = "LEX_TLS_SMOKE"
CA_CERT = "ca.crt"
CA_KEY = "ca.key"
SERVER_CERT = "server.crt"
SERVER_KEY = "server.key"
TRUSTED_CERT = "trusted.crt"
CLIENT_CERT = "client.crt"
CLIENT_KEY = "client.key"


def _tls_dir() -> Path:
    return Path(settings.orthanc_config_path).parent / "dicom-tls"


def _tls_path(name: str) -> str:
    return str(_tls_dir() / name)


def _orthanc_host() -> str:
    url = settings.orthanc_url.rstrip("/")
    if "://" in url:
        return url.split("://", 1)[1].split(":", 1)[0]
    return url.split(":", 1)[0]


def _orthanc_port() -> int:
    config = _read_config()
    try:
        return int(config.get("DicomPort") or 4242)
    except (TypeError, ValueError):
        return 4242


def _cert_status() -> dict[str, bool]:
    base = _tls_dir()
    names = [CA_CERT, SERVER_CERT, SERVER_KEY, TRUSTED_CERT, CLIENT_CERT, CLIENT_KEY]
    present = {name: (base / name).is_file() for name in names}
    return {
        "ca_present": present[CA_CERT],
        "server_present": present[SERVER_CERT] and present[SERVER_KEY],
        "trusted_present": present[TRUSTED_CERT],
        "client_present": present[CLIENT_CERT] and present[CLIENT_KEY],
        "ready": all(present.values()),
    }


def read_dicom_tls_orthanc_settings() -> dict[str, Any]:
    config = _read_config()
    cfg = get_dicom_tls_config()
    return {
        "enabled": bool(config.get("DicomTlsEnabled")),
        "remote_certificate_required": bool(config.get("DicomTlsRemoteCertificateRequired")),
        "min_protocol_version": int(config.get("DicomTlsMinimumProtocolVersion") or 0),
        "certificate": str(config.get("DicomTlsCertificate") or ""),
        "private_key": str(config.get("DicomTlsPrivateKey") or ""),
        "trusted_certificates": str(config.get("DicomTlsTrustedCertificates") or ""),
        "configured_enabled": bool(cfg["enabled"]),
    }


def apply_dicom_tls_orthanc_settings() -> dict[str, Any]:
    cfg = get_dicom_tls_config()
    config = _read_config()
    certs = _cert_status()
    changed = False

    if cfg["enabled"]:
        if not certs["server_present"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Certificado do servidor ausente. Gere ou importe os arquivos TLS antes de habilitar.",
            )
        desired = {
            "DicomTlsEnabled": True,
            "DicomTlsCertificate": _tls_path(SERVER_CERT),
            "DicomTlsPrivateKey": _tls_path(SERVER_KEY),
            "DicomTlsTrustedCertificates": _tls_path(TRUSTED_CERT),
            "DicomTlsRemoteCertificateRequired": bool(cfg["remote_certificate_required"]),
            "DicomTlsMinimumProtocolVersion": int(cfg["min_protocol_version"]),
        }
        for key, value in desired.items():
            if config.get(key) != value:
                config[key] = value
                changed = True
    else:
        if config.get("DicomTlsEnabled"):
            config["DicomTlsEnabled"] = False
            changed = True

    if changed:
        _write_config(config)
    return read_dicom_tls_orthanc_settings()


def _write_pem(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _generate_dev_certificates(*, common_name: str = "LEXPACS") -> None:
    base = _tls_dir()
    base.mkdir(parents=True, exist_ok=True)

    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "LEX PACS DICOM CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC))
        .not_valid_after(datetime.now(UTC) + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    def _sign_entity(cn: str, san: list[x509.GeneralName]) -> tuple[bytes, bytes]:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        builder = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .issuer_name(ca_name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(UTC))
            .not_valid_after(datetime.now(UTC) + timedelta(days=825))
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH, ExtendedKeyUsageOID.SERVER_AUTH]),
                critical=False,
            )
        )
        cert = builder.sign(ca_key, hashes.SHA256())
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        key_pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
        return cert_pem, key_pem

    host = _orthanc_host()
    server_san = [
        x509.DNSName("localhost"),
        x509.DNSName(host),
        x509.DNSName("server"),
    ]
    try:
        server_san.append(x509.IPAddress(ipaddress.ip_address(socket.gethostbyname(host))))
    except (OSError, ValueError):
        pass

    server_cert, server_key = _sign_entity(common_name, server_san)
    client_aet = str(get_dicom_tls_config()["smoke_consumer_aet"])
    client_cert, client_key = _sign_entity(client_aet, [x509.DNSName("portal")])

    ca_pem = ca_cert.public_bytes(serialization.Encoding.PEM)
    _write_pem(base / CA_CERT, ca_pem)
    _write_pem(
        base / CA_KEY,
        ca_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ),
    )
    _write_pem(base / SERVER_CERT, server_cert)
    _write_pem(base / SERVER_KEY, server_key)
    _write_pem(base / TRUSTED_CERT, ca_pem)
    _write_pem(base / CLIENT_CERT, client_cert)
    _write_pem(base / CLIENT_KEY, client_key)


def generate_dev_certificates(*, actor: str) -> dict[str, Any]:
    called_aet = str(_read_config().get("DicomAet") or "LEXPACS")
    _generate_dev_certificates(common_name=called_aet)
    record_dicom_tls_generated(actor=actor)
    return build_dicom_tls_status_payload()


def build_dicom_tls_status_payload() -> dict[str, Any]:
    orthanc = read_dicom_tls_orthanc_settings()
    certs = _cert_status()
    cfg = get_dicom_tls_config()
    return {
        "config": cfg,
        "stats": get_dicom_tls_stats(),
        "orthanc": orthanc,
        "certificates": {
            **_cert_status(),
            "directory": str(_tls_dir()),
            "server_certificate": _tls_path(SERVER_CERT),
            "server_private_key": _tls_path(SERVER_KEY),
            "trusted_certificates": _tls_path(TRUSTED_CERT),
            "client_certificate": _tls_path(CLIENT_CERT),
        },
        "dicom_aet": str(_read_config().get("DicomAet") or "LEXPACS"),
        "dicom_port": _orthanc_port(),
        "tls_ready": bool(cfg["enabled"]) and certs["server_present"] and orthanc["enabled"],
    }


def _ensure_smoke_consumer_modality() -> str:
    cfg = get_dicom_tls_config()
    aet = str(cfg["smoke_consumer_aet"])
    orthanc_host = _orthanc_host()
    orthanc_port = _orthanc_port()
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect((orthanc_host, orthanc_port))
        consumer_host = probe.getsockname()[0]
        probe.close()
    except OSError:
        consumer_host = "portal"

    config = _read_config()
    modalities = dict(config.get("DicomModalities") or {})
    entry = {
        "AET": aet,
        "Host": consumer_host,
        "Port": 4242,
        "AllowEcho": True,
        "AllowFind": False,
        "AllowMove": False,
        "AllowGet": False,
        "AllowStore": False,
    }
    if modalities.get(TLS_MODALITY_KEY) != entry:
        modalities[TLS_MODALITY_KEY] = entry
        config["DicomModalities"] = modalities
        _write_config(config)
    return aet


def test_dicom_tls_echo(*, actor: str) -> dict[str, Any]:
    cfg = get_dicom_tls_config()
    orthanc = read_dicom_tls_orthanc_settings()
    if not cfg["enabled"] or not orthanc["enabled"]:
        record_dicom_tls_test(actor=actor, success=False, error="DICOM TLS desabilitado.")
        return {"success": False, "error": "DICOM TLS desabilitado."}

    certs = _cert_status()
    if not certs["server_present"] or not certs["trusted_present"]:
        record_dicom_tls_test(actor=actor, success=False, error="Certificados TLS ausentes.")
        return {"success": False, "error": "Certificados TLS ausentes."}

    calling_aet = _ensure_smoke_consumer_modality()
    called_aet = str(_read_config().get("DicomAet") or "LEXPACS")
    host = _orthanc_host()
    port = _orthanc_port()
    ca_file = _tls_dir() / CA_CERT

    try:
        import ssl

        from pynetdicom import AE
        from pynetdicom.sop_class import Verification
    except ImportError as exc:
        record_dicom_tls_test(actor=actor, success=False, error="pynetdicom ausente.")
        return {"success": False, "error": "pynetdicom ausente."}

    tls_ctx = ssl.create_default_context(cafile=str(ca_file))
    tls_ctx.check_hostname = False
    tls_ctx.verify_mode = ssl.CERT_REQUIRED
    if cfg["remote_certificate_required"]:
        if not certs["client_present"]:
            record_dicom_tls_test(actor=actor, success=False, error="Certificado cliente ausente.")
            return {"success": False, "error": "Certificado cliente ausente."}
        tls_ctx.load_cert_chain(_tls_path(CLIENT_CERT), _tls_path(CLIENT_KEY))

    ae = AE(ae_title=calling_aet)
    ae.add_requested_context(Verification)

    try:
        assoc = ae.associate(host, port, ae_title=called_aet, tls_args=(tls_ctx, host))
        if not assoc.is_established:
            record_dicom_tls_test(actor=actor, success=False, error="Associação DICOM TLS rejeitada.")
            return {"success": False, "error": "Associação DICOM TLS rejeitada."}
        status = assoc.send_c_echo()
        assoc.release()
    except Exception as exc:
        logger.warning("C-ECHO TLS falhou: %s", exc)
        record_dicom_tls_test(actor=actor, success=False, error=str(exc))
        return {"success": False, "error": str(exc)}

    if not status or status.Status != 0x0000:
        msg = f"C-ECHO TLS falhou (status 0x{status.Status:04X})." if status else "C-ECHO TLS sem resposta."
        record_dicom_tls_test(actor=actor, success=False, error=msg)
        return {"success": False, "error": msg}

    record_dicom_tls_test(actor=actor, success=True)
    return {
        "success": True,
        "calling_aet": calling_aet,
        "called_aet": called_aet,
        "host": host,
        "port": port,
    }
