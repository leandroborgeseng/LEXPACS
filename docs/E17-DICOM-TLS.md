# E17 — DICOM TLS (porta 4242)

**Status:** planejado para v1.0 · ver também [TLS-E-DOMINIO.md](./TLS-E-DOMINIO.md) (HTTP/HTTPS)

## Objetivo

Criptografar associações DICOM na porta **4242** (modalidades → PACS).

## Configuração Orthanc (referência)

No `orthanc.json` (volume `server-config`), após gerar certificado e chave:

```json
{
  "DicomTlsEnabled": true,
  "DicomTlsCertificate": "/orthanc-config/dicom-tls.crt",
  "DicomTlsPrivateKey": "/orthanc-config/dicom-tls.key",
  "DicomTlsTrustedCertificates": "/orthanc-config/dicom-tls-ca.pem",
  "DicomTlsRemoteCertificateRequired": true
}
```

Montar os arquivos via volume ou init container. Reinício do serviço `server` após alteração.

## Modalidades

Cada equipamento deve:

- Confiar na CA do PACS (ou certificado autoassinado importado)
- Usar **TLS** na associação DICOM (não apenas TCP)
- Manter AE Title e IP/host alinhados com a aba **Equipamentos** (E16)

## LEX PACS — entrega prevista

- UI na aba Servidor: toggle TLS + caminhos dos certificados (somente leitura dos paths no volume)
- Documentação de geração com `openssl` ou certificado interno da clínica
- Smoke test `E17` (associação TLS com `storescu`/`echoscu` do DCMTK)

## Homologação atual

Sem TLS na 4242: aceitável em rede VLAN isolada; **não** recomendado para tráfego DICOM pela internet.
