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
├── ohif-viewer_orthanc-storage.tar.gz
├── ohif-viewer_orthanc-config.tar.gz
├── ohif-viewer_lex-reports.tar.gz
├── ohif-viewer_lex-audit.tar.gz
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
