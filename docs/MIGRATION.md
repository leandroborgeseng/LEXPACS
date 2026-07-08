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
- `QueryRetrieveSize` no Orthanc (padrão 100) pode limitar quantos estudos um único C-FIND retorna — use **filtros por intervalo de datas** e várias descobertas para PACS com dezenas de milhares de exames.

## Descoberta retorna 0 estudos

| Verificação | Detalhe |
|-------------|---------|
| **Salvar** antes de descobrir | Clique em *Salvar configuração* após preencher origem |
| **C-ECHO** | Deve passar antes do C-FIND |
| **AE Title** | AE do PACS **remoto** (ex.: `ORTHANC`, `PACS1`), não o AE local (`LEXPACS`) |
| **Porta** | Orthanc usa **4242**; PACS clássicos usam **104** |
| **Host** | IP **alcançável do container `server`**, não `localhost` |
| **Filtros de data** | Deixe vazios na 1ª tentativa; datas erradas excluem tudo |
| **Firewall** | PACS remoto deve aceitar C-FIND do IP do LEX PACS |
| **C-MOVE destino** | PACS remoto precisa conhecer `LEXPACS` @ IP:4242 para importar depois |

Para ~10 mil exames: descubra em lotes, ex.: `20200101`–`20221231`, depois `20230101`–`20251231` (salve e *Descobrir* por intervalo; a fila acumula se não resetar).
