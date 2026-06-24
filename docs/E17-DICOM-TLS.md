# E17 — DICOM TLS (porta 4242)

**Status:** concluído — painel Servidor + certificados no volume + smoke `E17`

Ver também [TLS-E-DOMINIO.md](./TLS-E-DOMINIO.md) (HTTP/HTTPS do portal).

## Objetivo

Criptografar associações DICOM na porta **4242** (modalidades → PACS) via TLS DIMSE no Orthanc.

## Portal LEX

| Recurso | Descrição |
|---------|-----------|
| `GET /clinica-api/admin/pacs/dicom-tls/status` | Status TLS, certificados e Orthanc |
| `PUT /clinica-api/admin/pacs/dicom-tls/config` | Habilitar/desabilitar TLS, exigir cert. cliente |
| `POST /clinica-api/admin/pacs/dicom-tls/generate` | Gera CA + par servidor/cliente (desenvolvimento) |
| `POST /clinica-api/admin/pacs/dicom-tls/test-echo` | C-ECHO TLS via `pynetdicom` (SSL) |

Na aba **Servidor** das configurações PACS: toggle TLS, gerar certificados de dev e testar C-ECHO.

Certificados ficam em `/orthanc-config/dicom-tls/` (volume `server-config`):

- `server.crt` / `server.key` — Orthanc SCP
- `trusted.crt` — CAs confiáveis (peers)
- `ca.crt` — CA de desenvolvimento
- `client.crt` / `client.key` — cliente smoke / mTLS

## Orthanc (`orthanc.json`)

```json
{
  "DicomTlsEnabled": true,
  "DicomTlsCertificate": "/orthanc-config/dicom-tls/server.crt",
  "DicomTlsPrivateKey": "/orthanc-config/dicom-tls/server.key",
  "DicomTlsTrustedCertificates": "/orthanc-config/dicom-tls/trusted.crt",
  "DicomTlsRemoteCertificateRequired": false,
  "DicomTlsMinimumProtocolVersion": 0
}
```

O entrypoint do Orthanc reinicia o processo ao detectar alteração em `orthanc.json`.

## Modalidades

Cada equipamento deve:

- Confiar na CA do PACS (ou importar o certificado autoassinado)
- Usar **TLS** na associação DICOM (não apenas TCP)
- Manter AE Title e IP alinhados com a aba **Equipamentos** (E16)

**Fallback legado:** TLS desabilitado por padrão — adequado para VLAN isolada sem criptografia DIMSE.

## Produção

Substitua os PEM de desenvolvimento pelos certificados da clínica (PKI interna ou CA hospitalar). Ajuste `DicomTlsRemoteCertificateRequired` se as modalidades suportam mTLS.

## Smoke

```bash
./ohif-viewer/scripts/smoke-test.sh E17
```

Habilita TLS temporariamente, valida C-ECHO DIMSE com `pynetdicom` e restaura TCP legado ao final (se não estava ativo antes).
