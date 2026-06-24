# E21 — Query/Retrieve (C-FIND / C-MOVE / C-GET)

**Status:** concluído — SCP Orthanc + painel Integração + smoke `E21`

## O que funciona

O Orthanc expõe SCP DICOM na porta **4242** com suporte a:

- **C-ECHO** — teste de conectividade
- **C-STORE** — ingestão de modalidades cadastradas
- **C-FIND / C-MOVE / C-GET** — consulta e recuperação DIMSE

Com **E16** ativo (`DicomAlwaysAllowFind/Move/Get: false`), apenas AE Titles cadastrados na aba **Equipamentos** (com `AllowFind`, `AllowMove`, `AllowGet`) podem consultar ou recuperar.

## Portal LEX

| Recurso | Descrição |
|---------|-----------|
| `GET /clinica-api/admin/pacs/qr/status` | Status SCP, política Q/R, consumidores cadastrados |
| `PUT /clinica-api/admin/pacs/qr/config` | `QueryRetrieveSize` e AE do smoke consumer |
| `POST /clinica-api/admin/pacs/qr/test-find` | C-FIND Study level via `pynetdicom` (admin) |

Na aba **Integração** das configurações PACS: status Q/R e botão **Testar C-FIND Study**.

O startup do portal aplica `QueryRetrieveSize` e força `DicomAlwaysAllowMove/Get: false` em `orthanc.json` (sem alterar `DicomAlwaysAllowFind`, controlado por E16).

## Configuração recomendada

1. Cadastrar o sistema consumidor (viewer legado, outro PACS, broker) como modalidade DICOM com AE + IP
2. Marcar `AllowFind` / `AllowMove` / `AllowGet` conforme o uso
3. Para migração **deste** PACS como origem, usar AE `LEXPACS` e filtros na aba **Migração**

## Homologação

Para piloto clínico (só C-STORE + MWL + viewer web), Q/R externo é opcional. Necessário para **PACS federado** ou integração com broker DICOM hospitalar.

## Smoke

```bash
./ohif-viewer/scripts/smoke-test.sh E21
```

Valida política restrita, `QueryRetrieveSize`, C-FIND DIMSE e presença de `AllowFind` em `DicomModalities`.
