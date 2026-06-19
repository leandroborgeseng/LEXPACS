# LEXPACS

PACS clínico white-label — visualizador DICOM, worklist, laudos, portal do paciente e gateway unificado.

**Versão:** 0.7.0

## Documentação

| Documento | Conteúdo |
|-----------|----------|
| [docs/MANUAL-LEX-PACS.md](docs/MANUAL-LEX-PACS.md) | Operação, arquitetura, segurança |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Roadmap de produto |
| [docs/I18N.md](docs/I18N.md) | Traduções (pt-BR, en-US, es) e tema claro/escuro |
| [docs/BACKUP.md](docs/BACKUP.md) | Backup, retenção e restore |
| [docs/UPGRADE.md](docs/UPGRADE.md) | Upgrade e rollback |
| [ohif-viewer/.env.example](ohif-viewer/.env.example) | Variáveis de ambiente |

## Início rápido

```bash
cd ohif-viewer
cp .env.example .env
docker compose up -d
```

Acesso: `http://localhost:3000`
