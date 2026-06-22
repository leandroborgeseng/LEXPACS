# E19 — MPPS (Modality Performed Procedure Step)

**Status:** planejado para v1.0 · base documentada

## Objetivo

Receber **N-CREATE / N-SET** MPPS das modalidades para marcar procedimentos como realizados e alinhar worklist/RIS.

## Situação atual (v0.8)

- MWL via plugin Worklists + SQL/HL7 ✅
- MPPS SCP dedicado ❌ (não habilitado no `orthanc.base.json`)

## Próximo passo técnico

1. Verificar plugin MPPS na imagem `jodogne/orthanc-plugins` (ou build custom)
2. Adicionar em `Plugins` e configurar seção `ModalityPerformedProcedureStep` no `orthanc.json`
3. Portal: endpoint interno ou job que atualiza `lex_mwl_schedule` / auditoria ao receber MPPS
4. Smoke test `E19` em `ohif-viewer/scripts/smoke-test.sh`

## Integração RIS

| Canal | Uso |
|-------|-----|
| DICOM MPPS | Modalidade → PACS (padrão DICOM) |
| HL7 ORU/ORM | Opcional: PACS → RIS após MPPS (fase posterior) |

## Homologação sem MPPS

Clínicas que só precisam de armazenamento + MWL + laudo podem operar sem MPPS; equipamentos que exigem MPPS devem aguardar E19 ou usar gateway DICOM externo.
