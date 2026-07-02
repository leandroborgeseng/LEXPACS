# LEX PACS — Backup e restore (E5)

Guia operacional para backup manual, retenção e restore.

---

## Backup manual (3 comandos)

```bash
cd ohif-viewer
./scripts/backup-volumes.sh ./backups          # 1. snapshot
./scripts/verify-backup.sh ./backups/YYYY-MM-DD_HHMMSS   # 2. validar
./scripts/backup-retention.sh ./backups        # 3. aplicar retenção
```

## Backup automático

```bash
docker compose --profile backup up -d backup
```

Variáveis (`.env`):

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `BACKUP_INTERVAL_HOURS` | `24` | Intervalo entre backups |
| `BACKUP_RETENTION_DAILY` | `7` | Dias distintos mantidos |
| `BACKUP_RETENTION_WEEKLY` | `4` | Semanas adicionais (1 snapshot/semana) |

Status na UI: **Admin → Configurações DICOM → Backup**, ou `GET /clinica-api/admin/pacs/backup/status`.

## Backup remoto (Railway / S3)

Para espelhar snapshots para volume Railway ou bucket S3 (imagens, banco, configs), configure `BACKUP_REMOTE_DIR` e/ou `BACKUP_S3_*` — ver **[BACKUP-RAILWAY-S3.md](./BACKUP-RAILWAY-S3.md)**.

## Política de retenção

1. **7 diários** — o backup mais recente de cada um dos últimos 7 dias.
2. **4 semanais** — o backup mais recente de cada semana ISO anterior ao período diário.

Implementação: `ohif-viewer/scripts/backup-retention.py`.

## Restore

```bash
cd ohif-viewer
./scripts/restore-backup.sh ./backups/YYYY-MM-DD_HHMMSS
docker compose up -d
./scripts/smoke-test.sh
```

**Atenção:** restore substitui dados nos volumes. Faça backup antes em produção.

## Estrutura do snapshot

```
backups/YYYY-MM-DD_HHMMSS/
├── manifest.json
├── *_server-data.tar.gz          # DICOM / Orthanc storage
├── *_server-config.tar.gz        # orthanc.json, TLS, etc.
├── *_server-worklists.tar.gz
├── *_lex-reports.tar.gz
├── *_lex-audit.tar.gz
├── postgres.dump
└── htpasswd                 # se existir
```

## Testes

```bash
./scripts/smoke-test.sh E5
./scripts/verify-backup.sh /tmp/lex-pacs-smoke-backup/<stamp>
./scripts/e2e-test.sh
```

Ver também [UPGRADE.md](./UPGRADE.md) (backup obrigatório antes de upgrade).
