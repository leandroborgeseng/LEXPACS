# E19 — MPPS (Modality Performed Procedure Step)

**Status:** concluído (v0.9) · smoke `E19`

## Objetivo

Receber **N-CREATE / N-SET** MPPS das modalidades para marcar procedimentos como realizados e remover entradas da agenda MWL.

## Entrega

- Servidor **MPPS SCP** no portal (`pynetdicom`) — porta **4243** (AET padrão `LEXMPPS`)
- Ao receber status **COMPLETED** (ou **DISCONTINUED**, se habilitado), remove linha em `lex_mwl_schedule` e arquivo `.wl`
- API admin: `GET/PUT /clinica-api/admin/pacs/mpps/*`, `POST .../mpps/simulate`
- UI: aba **Integração → MPPS** nas Configurações do Servidor

## Configurar modalidade

| Campo | Valor típico |
|-------|----------------|
| MPPS AE Title | `LEXMPPS` |
| Host | IP do servidor LEX PACS |
| Porta | `4243` (não usar 4242 — Orthanc C-STORE) |

## Teste

```bash
./ohif-viewer/scripts/smoke-test.sh E19
```

## Integração RIS

| Canal | Uso |
|-------|-----|
| DICOM MPPS | Modalidade → PACS (padrão DICOM) |
| HL7 ORU/ORM | Opcional: PACS → RIS após MPPS (fase posterior) |
