# Armazenamento e backup (LEX PACS)

## Onde configurar

**Configurações DICOM** → aba **Armazenamento** (engrenagem na worklist).

| Área | Conteúdo |
|------|----------|
| Estatísticas | Volume DICOM, laudos, auditoria, idade dos exames |
| Backup | Status, política (intervalo/retenção), **Executar backup agora** |
| Compressão | Regras por idade (`StudyDate`) e modalidade, execução manual ou agendada |

A aba **Operação** mantém apenas rate limit de login e auditoria.

## Backup automático (Coolify / compose)

O serviço `backup` no `docker-compose.coolify.yml` executa `backup-scheduler.sh`:

- Lê política de `portal-ops.env` (volume `server-config`, gravado pela UI)
- Faz dump dos volumes `lex-pacs_*` + PostgreSQL
- Grava `latest-status.json` em `lex-backups`

**Backup manual:** botão na UI grava `backup-trigger` em `server-config`; o sidecar executa no próximo ciclo do scheduler.

## Compressão pós-processamento

Diferente da **transcodificação na ingestão** (aba Servidor):

1. Regras definem idade mínima em anos, modalidades (opcional) e transfer syntax alvo
2. O worker do portal descobre exames elegíveis via Orthanc REST
3. Cada instância é regravada com `POST /instances/{id}/modify` + `Transcode`

Recomendação piloto: começar com lote pequeno (`batch_size: 2`) e uma regra conservadora (ex.: CT/MR > 2 anos → JPEG-LS).

## API admin

| Método | Rota |
|--------|------|
| `GET` | `/clinica-api/admin/pacs/storage/status` |
| `PUT` | `/clinica-api/admin/pacs/storage/config` |
| `POST` | `/clinica-api/admin/pacs/storage/start` |
| `POST` | `/clinica-api/admin/pacs/storage/pause` |
| `POST` | `/clinica-api/admin/pacs/storage/reset` |
| `POST` | `/clinica-api/admin/pacs/backup/trigger` |

Estado persistido em `lex-pacs-settings.json` (`storage_policies`) e `storage-queue.json`.
