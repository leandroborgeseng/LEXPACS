# Migração PACS → LEX PACS

Importação **resumível** de exames de um PACS DICOM legado para o LEX PACS.

## Fluxo

1. **Configurar origem** — aba *Migração* nas configurações do servidor (AE Title, host, porta).
2. **Testar conexão** — C-ECHO no PACS remoto.
3. **Descobrir estudos** — C-FIND (nível Study) com filtros opcionais (data, Patient ID, modalidade).
4. **Iniciar / Retomar** — C-MOVE estudo a estudo para o AE local (`LEXPACS`).
5. **Pausar** — a qualquer momento; o cursor é salvo em `lex-pacs-settings.json`.
6. **Resetar** — limpa fila e estatísticas (após pausar).

## Persistência

| Arquivo | Conteúdo |
|---------|----------|
| `lex-pacs-settings.json` → `pacs_migration` | Config, status, cursor, estatísticas |
| `migration-queue.json` | Lista de estudos descobertos (StudyInstanceUID) |

Após reinício do portal, migrações com status `running` são retomadas automaticamente.

## Requisitos de rede

- O PACS de **origem** deve aceitar C-ECHO e C-FIND do LEX PACS.
- O PACS de **origem** deve conseguir C-MOVE para o AE `LEXPACS` na porta 4242 do servidor LEX.
- Cadastre o IP do LEX PACS no firewall e no PACS remoto como destino de movimentação.

## API (admin)

| Método | Endpoint |
|--------|----------|
| GET | `/clinica-api/admin/pacs/migration/status` |
| PUT | `/clinica-api/admin/pacs/migration/config` |
| POST | `/clinica-api/admin/pacs/migration/test-echo` |
| POST | `/clinica-api/admin/pacs/migration/discover` |
| POST | `/clinica-api/admin/pacs/migration/start` |
| POST | `/clinica-api/admin/pacs/migration/pause` |
| POST | `/clinica-api/admin/pacs/migration/reset` |

## Limitações atuais

- Apenas PACS com **DIMSE** (C-FIND/C-MOVE); DICOMweb (STOW-RS) é roadmap E21b.
- Descoberta carrega todos os estudos na memória/fila — volumes muito grandes (>100k) podem exigir filtros por data.
- Um estudo por vez por padrão (`batch_size=1`) para estabilidade em migrações longas.
