# LEX PACS — Upgrade de versão (E6)

Runbook para atualizar o LEX PACS em produção com **backup obrigatório**, **tags fixas** e **rollback documentado**.

**Pré-requisitos:** etapa E5 (backup) funcional; acesso SSH ao servidor; janela de manutenção curta.

---

## Versões e imagens

| Componente | Tag / versão |
|------------|----------------|
| Produto LEX PACS | `ohif-viewer/LEX_PACS_VERSION` (ex. `0.4.0`) |
| Viewer | `lex-pacs/viewer:${LEX_PACS_VERSION}` |
| Portal / API | `lex-pacs/portal:${LEX_PACS_VERSION}` |
| Servidor DICOM | `jodogne/orthanc-plugins:1.12.5` (fixa no compose) |
| Gateway | `nginx:1.27-alpine` |

**Nunca use `latest`** para viewer e portal em produção.

---

## Upgrade padrão (recomendado)

Na pasta `ohif-viewer`:

```bash
# 1. Conferir versão atual
cat LEX_PACS_VERSION

# 2. Upgrade automatizado (backup + rebuild + smoke test)
chmod +x scripts/upgrade.sh scripts/rollback.sh scripts/restore-backup.sh
./scripts/upgrade.sh 0.4.1
```

O script `upgrade.sh`:

1. Executa `backup-volumes.sh` em `./backups/`
2. Atualiza `LEX_PACS_VERSION`
3. `docker compose build --pull` e `up -d`
4. Roda migrações (`migrate.sh`) se existirem (futuro E3)
5. Executa `./scripts/smoke-test.sh`

---

## Upgrade manual (passo a passo)

```bash
cd ohif-viewer

# 0. Migração E3 (apenas na primeira vez, vindo de SQLite)
./scripts/migrate-e3.sh

# 1. Backup
./scripts/backup-volumes.sh /var/backups/lex-pacs

# 2. Definir nova versão
echo "0.4.1" > LEX_PACS_VERSION
export LEX_PACS_VERSION=0.4.1

# 3. Atualizar imagens LEX PACS
docker compose build --pull
docker compose up -d

# 4. Migrações (quando houver PostgreSQL — E3)
# ./scripts/migrate.sh

# 5. Validar
./scripts/smoke-test.sh
```

### Atualizar Orthanc ou Nginx

Edite `docker-compose.yml` com a nova tag fixa, faça backup e:

```bash
docker compose pull orthanc gateway
docker compose up -d orthanc gateway
./scripts/smoke-test.sh
```

---

## Rollback

### Rollback só de versão (dados intactos)

Volta viewer e portal para a tag anterior. **Volumes não são alterados.**

```bash
./scripts/rollback.sh 0.4.0
```

### Rollback com restore de backup

Se o upgrade corrompeu dados ou migração falhou:

```bash
./scripts/rollback.sh 0.4.0 ./backups/2026-06-18_143000
# ou apenas restore:
./scripts/restore-backup.sh ./backups/2026-06-18_143000
./scripts/smoke-test.sh
```

O `manifest.json` do backup contém `lex_pacs_version` e lista de imagens no momento do snapshot.

---

## Checklist pós-upgrade

- [ ] `./scripts/smoke-test.sh` — 0 falhas
- [ ] Worklist abre com credenciais clínicas
- [ ] Portal do paciente — login e lista de exames
- [ ] Laudo de um exame existente ainda acessível
- [ ] Modalidade consegue C-STORE (porta 4242)
- [ ] Versão no health: `curl -s http://localhost:3000/paciente-api/health | jq .version`

---

## Desenvolvimento

Upgrade rápido sem backup (não usar em produção):

```bash
SKIP_BACKUP=1 ./scripts/upgrade.sh 0.4.1
```

---

## Relacionados

- [TESTES.md](./TESTES.md) — smoke tests por etapa
- [MANUAL-LEX-PACS.md](./MANUAL-LEX-PACS.md) — operação geral
- [ROADMAP.md](./ROADMAP.md) — E5 backup, E3 migrações futuras
