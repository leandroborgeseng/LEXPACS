# E21 — Query/Retrieve (C-FIND / C-MOVE / C-GET)

**Status:** parcial — Orthanc SCP nativo; restrições E16 aplicam-se

## O que já funciona

O Orthanc expõe SCP DICOM na porta **4242** com suporte a:

- **C-ECHO** — teste de conectividade (smoke tests, migração)
- **C-STORE** — ingestão de modalidades cadastradas
- **C-FIND / C-MOVE** — consulta e recuperação (usado na migração PACS→PACS)

Com **E16** ativo (`DicomAlwaysAllowFind: false`), apenas AE Titles cadastrados na aba **Equipamentos** podem consultar/mover.

## Configuração recomendada

1. Cadastrar o sistema consumidor (viewer legado, outro PACS, broker) como modalidade DICOM com AE + IP
2. Se o consumidor for apenas **SCU** (só consulta/move para fora), ainda assim cadastrar como entrada em `DicomModalities`
3. Para migração **deste** PACS como origem, usar AE `LEXPACS` e filtros na aba **Migração**

## C-GET

Orthanc suporta C-GET quando habilitado na configuração; validar na versão 1.12+ do plugin. Teste com `getscu` do DCMTK apontando para `LEXPACS@host:4242`.

## Próximos passos LEX

- Painel **Operação** ou **Integração**: status Q/R + log de últimas operações FIND/MOVE
- Smoke test dedicado `E21` (FIND Study level + MOVE 1 estudo de teste)
- Documentar AE de destino para C-MOVE (Orthanc exige modalidade destino cadastrada)

## Homologação

Para piloto clínico (só C-STORE + MWL + viewer web), Q/R externo é opcional. Necessário para **PACS federado** ou integração com broker DICOM hospitalar.
