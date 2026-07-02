# Backup remoto — Railway (volume ou bucket S3)

Guia para espelhar backups do LEX PACS (imagens DICOM, PostgreSQL, configurações Orthanc, laudos, auditoria) para armazenamento remoto no Railway, liberando espaço no disco local.

---

## O que é copiado

Cada snapshot em `backups/YYYY-MM-DD_HHMMSS/` contém:

| Artefato | Conteúdo |
|----------|----------|
| `*_server-data.tar.gz` | Imagens e estudos DICOM (Orthanc) |
| `*_server-config.tar.gz` | `orthanc.json`, TLS, MPPS, Q/R, etc. |
| `*_server-worklists.tar.gz` | Worklists MWL |
| `*_lex-reports.tar.gz` | Laudos |
| `*_lex-audit.tar.gz` | Trilha de auditoria |
| `postgres.dump` | Banco PostgreSQL (metadados Orthanc) |
| `manifest.json` | Versão e inventário do snapshot |

Após cada ciclo automático: retenção local (7 diários + 4 semanais) e **espelhamento** para o destino remoto (`backup-remote-mirror.sh`).

---

## Opção A — Volume Railway montado (recomendado se já tem disco S3 mapeado)

1. No painel Railway, crie ou anexe um **Volume** ao serviço/stack do LEX PACS.
2. Monte no container `backup` (ex.: `/railway-backups`).
3. No `.env.coolify` (ou variáveis Coolify/Railway):

```bash
BACKUP_REMOTE_DIR=/railway-backups
```

4. No `docker-compose.coolify.yml`, descomente o mount do volume no serviço `backup`:

```yaml
volumes:
  - lex-backups:/backups
  - railway-backups:/railway-backups   # nome do volume no Railway
```

5. Recrie o container backup:

```bash
docker compose -f docker-compose.coolify.yml --env-file .env.coolify up -d backup
```

O espelhamento usa `rsync -a --delete`: o remoto fica **idêntico** ao diretório local após retenção.

---

## Opção B — Bucket S3 (Railway Bucket)

1. Crie um **Bucket** no Railway e copie as credenciais (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, endpoint).
2. Configure no `.env.coolify`:

```bash
BACKUP_S3_BUCKET=nome-do-seu-bucket
BACKUP_S3_PREFIX=lex-pacs/producao
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_ENDPOINT_URL=https://storage.railway.app
AWS_DEFAULT_REGION=auto
```

3. Recrie o serviço `backup` (variáveis são lidas pelo scheduler).

O sync usa `aws s3 sync --delete` via imagem `amazon/aws-cli` (acesso ao socket Docker já existe no sidecar).

Estrutura no bucket:

```
s3://seu-bucket/lex-pacs/producao/
├── 2026-06-19_120000/
├── 2026-06-20_120000/
└── latest-status.json
```

---

## Opção C — Volume **e** S3

Defina `BACKUP_REMOTE_DIR` e `BACKUP_S3_BUCKET` juntos. Ambos recebem o mesmo espelho após cada backup.

---

## Fluxo automático

```
backup-scheduler.sh
  → backup-volumes.sh      (snapshot local em /backups)
  → backup-retention.sh    (limpa snapshots antigos localmente)
  → backup-remote-mirror.sh (rsync e/ou s3 sync --delete)
```

Intervalo: `BACKUP_INTERVAL_HOURS` (padrão 24h). Disparo manual: Admin → Backup → Executar agora.

---

## Backup manual com espelhamento

```bash
cd ohif-viewer
export BACKUP_ROOT=./backups
export BACKUP_REMOTE_DIR=/caminho/remoto   # ou vars S3
./scripts/backup-volumes.sh
./scripts/backup-retention.sh ./backups
./scripts/backup-remote-mirror.sh ./backups
```

---

## Restore a partir do remoto

**Volume Railway:** copie o snapshot desejado de volta para `./backups/` e use `restore-backup.sh`.

**S3:**

```bash
aws s3 sync s3://seu-bucket/lex-pacs/producao/2026-06-19_120000/ ./restore-staging/ \
  --endpoint-url https://storage.railway.app
cd ohif-viewer
./scripts/restore-backup.sh ../restore-staging
```

Ver [BACKUP.md](./BACKUP.md) para o fluxo completo de restore.

---

## Disco local cheio (Mac/servidor)

Com espelhamento ativo, o volume local `lex-backups` mantém apenas a janela de retenção (≈11 snapshots). O histórico de longo prazo fica no Railway — ideal quando o disco local está em ~94% como no seu Mac.

Para liberar espaço imediato no servidor de dev:

```bash
docker system prune -f
docker builder prune -f
```

Não apague `lex-backups` sem confirmar que o espelhamento remoto está OK.

---

## Troubleshooting

| Sintoma | Ação |
|---------|------|
| `Mirror remoto falhou` nos logs do `backup` | Verifique credenciais S3, endpoint e permissão de escrita no volume |
| S3 vazio | Confirme `BACKUP_S3_BUCKET` e que o container `backup` tem acesso à rede |
| Volume Railway vazio | Confirme mount em `/railway-backups` e `BACKUP_REMOTE_DIR` igual ao path |
| Backup local OK, remoto desatualizado | Veja logs: `docker logs backup --tail 80` |

---

Ver também: [BACKUP.md](./BACKUP.md), [UPGRADE.md](./UPGRADE.md).
