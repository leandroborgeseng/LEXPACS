# LEX PACS — Guia de testes por etapa

Validação incremental antes de avançar no [ROADMAP.md](./ROADMAP.md).

---

## Comando principal

```bash
cd ohif-viewer
chmod +x scripts/smoke-test.sh    # uma vez
./scripts/smoke-test.sh           # todas as etapas implementadas
./scripts/smoke-test.sh --list    # ver etapas disponíveis
./scripts/smoke-test.sh E5        # só uma etapa
./scripts/smoke-test.sh E1 E9 E10 # combinação
```

**Sucesso:** `0 falha` e exit code `0`.

---

## Etapas com testes automatizados

| ID | O que o script valida |
|----|------------------------|
| **Infra** | Containers (gateway, portal, ohif, orthanc), health, DICOMweb |
| **E1** | Portal, login paciente, lista exames, sem Swagger, marca LEX |
| **E2** | Auth worklist 401/200, cookie bloqueado, viewer paciente, worklist bloqueada |
| **E2b** | Título LEX PACS no HTML/manifest, sem "OHIF Viewer" |
| **E2c** | AE Title API = servidor DICOM |
| **E2d** | API `/clinica-api/` protegida |
| **E3** | PostgreSQL, orthanc-storage, migrate-e3, DICOMweb |
| **E4** | IngestTranscoding JPEG-LS lossless + GDCM |
| **E7** | API servidor/equipamentos + modal com abas |
| **E8** | Presets worklist, URL ?view=, auth preservada |
| **E5** | Script backup, volumes, manifest, postgres.dump |
| **E6** | Tags fixas, runbook UPGRADE.md, scripts upgrade/rollback, health.version |
| **E9** | Rascunho rich text (ou regressão se já assinado) |
| **E10** | Upload e download PDF |
| **E11** | Assinatura + bloqueio 403 pós-assinar |
| **E12** | Liberação clínica + portal paciente vê laudo/PDF |
| **E13** | Plugin MWL, sync SQL, filtro station_aet, arquivos .wl |
| **E14** | Keycloak OIDC + Bearer na API + Basic legado |
| **E15** | Log JSONL: study_open, mwl_sync, report_signed, export_pdf |

### Etapas pendentes (sem teste ainda)

Nenhuma — roadmap E1–E15 coberto pelo smoke test.

Rodar explicitamente: `./scripts/smoke-test.sh E7` → mostra "etapa ainda não implementada".

---

## Variáveis de ambiente

| Variável | Padrão |
|----------|--------|
| `GATEWAY_URL` | `http://localhost:3000` |
| `ORTHANC_URL` | `http://localhost:8042` |
| `CLINIC_USER` / `CLINIC_PASS` | `clinica` / `lexclinica2024` |
| `PATIENT_ID` / `PATIENT_BIRTH` | `+oYVjq` / `25/08/1947` |
| `SMOKE_BACKUP_DIR` | `/tmp/lex-pacs-smoke-backup` |

---

## Fluxo após cada implementação

```bash
docker compose up --build -d
./scripts/smoke-test.sh E<ID>    # etapa nova
./scripts/smoke-test.sh          # regressão completa
```

Checklist manual (2 min no browser): worklist → abrir exame → painel Laudo — ver seção no ROADMAP.

---

## Adicionar testes para nova etapa

1. Implementar a funcionalidade.
2. Editar `ohif-viewer/scripts/smoke-test.sh`:
   - Adicionar ID em `IMPLEMENTED_STAGES`.
   - Remover de `PENDING_STAGES`.
   - Criar bloco `if should_run EX; then ... fi`.
3. Documentar critérios nesta tabela.
4. Marcar concluída no ROADMAP só com smoke verde.

---

## Quando falhar

```bash
docker compose logs gateway patient-portal ohif orthanc --tail=80
./scripts/smoke-test.sh E<ID>
```

Corrigir na etapa atual; não acumular débito para a próxima.
