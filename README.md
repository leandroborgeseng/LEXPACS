# LEXPACS

PACS clínico white-label — visualizador DICOM, worklist, laudos, portal do paciente e gateway unificado.

**Versão:** 0.7.0

## Documentação

| Documento | Conteúdo |
|-----------|----------|
| [docs/MANUAL-LEX-PACS.md](docs/MANUAL-LEX-PACS.md) | Operação, arquitetura, segurança |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Roadmap de produto |
| [docs/I18N.md](docs/I18N.md) | Traduções (pt-BR, en-US, es) e tema claro/escuro |
| [docs/COOLIFY.md](docs/COOLIFY.md) | **Deploy Docker no Coolify** |
| [docs/DEPLOY-GITHUB-COOLIFY.md](docs/DEPLOY-GITHUB-COOLIFY.md) | **CI/CD GitHub Actions → Coolify** |
| [docs/BACKUP.md](docs/BACKUP.md) | Backup, retenção e restore |
| [docs/UPGRADE.md](docs/UPGRADE.md) | Upgrade e rollback |
| [ohif-viewer/.env.example](ohif-viewer/.env.example) | Variáveis de ambiente |

## Início rápido (Linux com Docker)

**Dependências no servidor:** apenas [Docker Engine](https://docs.docker.com/engine/install/) e o plugin **Docker Compose v2** (`docker compose`). Não é necessário Node.js, Python nem nginx no host (opcional para proxy na porta 80).

```bash
git clone <url-do-repositorio> lex-pacs && cd lex-pacs
cp .env.coolify.example .env.coolify
# Edite .env.coolify (URL, senhas, OIDC)
./scripts/validate-coolify-env.sh

# Desenvolvimento / teste local (porta 3000)
docker compose -f docker-compose.coolify.yml \
  -f docker-compose.coolify.local.yml \
  --env-file .env.coolify up -d --build

# Produção em VPS (TLS 80/443 com Caddy)
# docker compose -f docker-compose.coolify.yml -f docker-compose.tls.yml --env-file .env.coolify up -d --build
```

Acesso local: `http://localhost:3000` · Login clínico: `/clinica/login` · Portal paciente: `/paciente/`

Portas úteis (override local): **3000** HTTP gateway, **4242** DICOM, **8042** Orthanc (admin), **2575** HL7 MLLP.

Guia completo: [docs/COOLIFY.md](docs/COOLIFY.md)

## Início rápido (legado ohif-viewer)
