# Manual LEX PACS — Implementação, Operação e Segurança

**Versão do documento:** 1.0  
**Data:** junho/2026  
**Público:** equipe técnica, operação e implantação

---

## Sumário

1. [Visão geral do produto](#1-visão-geral-do-produto)
2. [Arquitetura](#2-arquitetura)
3. [Componentes e responsabilidades](#3-componentes-e-responsabilidades)
4. [URLs, portas e fluxos de acesso](#4-urls-portas-e-fluxos-de-acesso)
5. [Portal do paciente](#5-portal-do-paciente)
6. [Visualizador clínico](#6-visualizador-clínico)
7. [Identificação do paciente (Patient ID)](#7-identificação-do-paciente-patient-id)
8. [Implantação e operação](#8-implantação-e-operação)
9. [Auditoria de segurança](#9-auditoria-de-segurança)
10. [Auditoria de performance](#10-auditoria-de-performance)
11. [White-label e superfícies expostas](#11-white-label-e-superfícies-expostas)
12. [Checklist de produção](#12-checklist-de-produção)
13. [Roadmap de etapas](#13-roadmap-de-etapas)
14. [Anexo técnico interno](#14-anexo-técnico-interno)

---

## 1. Visão geral do produto

O **LEX PACS** é uma solução de armazenamento e visualização de exames de imagem médica (DICOM), composta por:

| Módulo | Função |
|--------|--------|
| **Gateway de acesso** | Ponto único de entrada HTTP; autenticação clínica; roteamento |
| **Visualizador clínico** | Worklist e visualização de estudos para a equipe da clínica |
| **Portal do paciente** | Login do paciente e lista de exames próprios |
| **Servidor de imagens** | Armazenamento DICOM, recepção de modalidades e API de imagens |

Toda a experiência voltada ao usuário final (clínica e paciente) deve apresentar apenas a marca **LEX PACS**.

---

## 2. Arquitetura

```
                    ┌─────────────────────────────────────────┐
                    │         Gateway (:3000)                 │
                    │  auth clínica │ cookie paciente         │
                    └───────┬───────────────┬─────────────────┘
                            │               │
              ┌─────────────┼───────────────┼─────────────┐
              ▼             ▼               ▼             ▼
        /viewer/      /paciente/      /dicom-web      /wado
     Visualizador    Portal API+UI    (imagens)      (imagens)
              │             │               └──────┬──────┘
              │             │                      ▼
              │             │              Servidor de imagens
              │             └──────────────────────┘
              └──────────────────────────────────────┘
```

**Princípio de segurança:** o paciente nunca recebe credenciais clínicas. Ele obtém um **cookie temporário** vinculado a **um único exame**, válido apenas para abrir o visualizador e carregar as imagens daquele estudo.

---

## 3. Componentes e responsabilidades

### 3.1 Gateway (`ohif-viewer/nginx/gateway.conf`)

- Escuta na porta **3000** (única porta HTTP exposta ao usuário em ambiente padrão).
- **Worklist clínica** (`/viewer/`): exige usuário e senha (HTTP Basic Auth).
- **Portal do paciente** (`/paciente/`): acesso público à tela de login.
- **API do portal** (`/paciente-api/`): backend do portal, mesma origem.
- **Imagens** (`/dicom-web`, `/wado`): clínica autenticada **ou** paciente com cookie de viewer válido.
- Validação interna de cookie via `auth_request` (rota `/internal/auth/viewer-cookie`, não acessível externamente).
- Headers de segurança: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`; `server_tokens off`.

### 3.2 Visualizador clínico (`ohif-viewer/`)

- Build estático servido internamente; acesso externo somente via gateway em `/viewer/`.
- Configuração de produto: `platform/app/public/config/default.js`.
- Tema LEX PACS: cinza + vermelho (`platform/ui-next/src/tailwind.css`).
- Logo: `lex-pacs-logo.svg` e componente `LexPacsLogo`.

### 3.3 Portal do paciente (`lex-pacs-portal/`)

- API REST + interface estática.
- Autenticação: **ID do paciente** + **data de nascimento** (validados contra o servidor de imagens).
- JWT em `localStorage` para sessão da lista de exames.
- Cookie `lex_viewer_token` (HttpOnly) para abrir um exame no visualizador.

### 3.4 Servidor de imagens (`ohif-viewer/orthanc/`)

- Recebe exames via **DICOM C-STORE** (porta 4242).
- Armazena arquivos e índice; expõe API HTTP interna na rede Docker.
- Em desenvolvimento, a porta 8042 pode estar exposta para depuração — **não publicar em produção**.

---

## 4. URLs, portas e fluxos de acesso

### 4.1 URLs para usuários

| URL | Público | Autenticação |
|-----|---------|--------------|
| `http://<host>:3000/` | Clínica | Redireciona para `/viewer/` |
| `http://<host>:3000/viewer/` | Clínica | Usuário/senha clínica |
| `http://<host>:3000/clinica-api/` | Clínica | API de configuração (AE Title) |
| `http://<host>:3000/viewer/?StudyInstanceUIDs=…` | Paciente | Cookie temporário |

### 4.2 Portas no host

| Porta | Serviço | Produção |
|-------|---------|----------|
| **3000** | Gateway (obrigatória) | Sim, preferencialmente atrás de HTTPS |
| **4242** | DICOM C-STORE (modalidades) | Sim, restrita por firewall/VPN |
| **8042** | API do servidor de imagens | **Não** — usar `docker-compose.prod.yml` |

### 4.3 Fluxo clínico

1. Acessar `/viewer/`.
2. Informar credenciais clínicas.
3. Navegar na worklist e abrir exames.

### 4.4 Fluxo paciente

1. Acessar `/paciente/`.
2. Informar ID do paciente e data de nascimento.
3. Clicar em **Visualizar exame**.
4. O sistema define cookie e redireciona para o visualizador com o UID do estudo.
5. O paciente **não** acessa a worklist completa (bloqueio sem cookie + UID).

---

## 5. Portal do paciente

### 5.1 Endpoints da API

| Método | Rota (via gateway) | Descrição |
|--------|-------------------|-----------|
| `GET` | `/paciente-api/health` | Saúde do serviço (`storage: true/false`) |
| `POST` | `/paciente-api/auth/login` | Login; retorna JWT |
| `GET` | `/paciente-api/studies` | Lista exames (Bearer JWT) |
| `POST` | `/paciente-api/studies/{uid}/viewer-session` | Cookie + URL de redirect |

Documentação interativa da API (**Swagger/ReDoc**) está **desabilitada** em produção.

A rota de validação de cookie **não** é acessível via `/paciente-api/auth/validate-viewer-cookie` (retorna 404); uso exclusivamente interno do gateway.

### 5.2 Variáveis de ambiente

| Variável | Descrição |
|----------|-----------|
| `PORTAL_JWT_SECRET` | Segredo para assinar JWT (mín. 32 caracteres aleatórios) |
| `PORTAL_FALLBACK_CODE` | Código opcional se paciente não tiver data no cadastro DICOM |
| `VIEWER_TOKEN_EXPIRE_MINUTES` | Validade do cookie de visualização (padrão: 30) |
| `COOKIE_SECURE` | `true` com HTTPS em produção |
| `OHIF_VIEWER_URL` | URL pública do gateway |

### 5.3 Geração de credenciais clínicas

```bash
cd ohif-viewer
./scripts/generate-htpasswd.sh usuario senha_forte
```

O arquivo `nginx/.htpasswd` **não deve ser commitado** em produção com senhas reais.

---

## 6. Visualizador clínico

### 6.1 Configuração principal (`default.js`)

- `routerBasename: '/viewer'`
- `defaultDataSourceName: 'dicomweb'`
- Fonte de dados: proxy relativo `/dicom-web` e `/wado`
- `friendlyName: 'LEX PACS'` (visível apenas em erros de conexão)
- `investigationalUseDialog.option: 'never'` — banner de uso investigacional desligado
- `showCPUFallbackMessage: false` — evita modal técnico de fallback de GPU
- `whiteLabeling` com logo LEX PACS

### 6.3 Configuração do AE Title (interface gráfica)

Na **worklist clínica** (`/viewer/`), abra o menu de configurações (ícone de engrenagem) → **Configurações DICOM**.

| Campo | Descrição |
|-------|-----------|
| **AE Title** | Nome DICOM do PACS (máx. 16 caracteres; A–Z, 0–9, `_`, espaço) |
| **Porta DICOM** | Somente leitura (padrão 4242) |

Ao salvar, a configuração é gravada no volume `orthanc-config` e o **servidor DICOM reinicia automaticamente** (5–10 segundos).

**API clínica** (protegida por autenticação da clínica):

```bash
# Consultar
curl -u clinica:SENHA http://localhost:3000/clinica-api/admin/pacs/settings

# Alterar AE Title
curl -u clinica:SENHA -X PUT http://localhost:3000/clinica-api/admin/pacs/settings \
  -H "Content-Type: application/json" \
  -d '{"dicom_aet":"LEXPACS"}'
```

Configure o **mesmo AE Title** na modalidade (destino C-STORE).

### 6.4 Build

```bash
cd ohif-viewer
docker compose build ohif
```

O build usa `PUBLIC_URL=/viewer/` para que assets carreguem corretamente atrás do gateway.

---

## 7. Identificação do paciente (Patient ID)

O **ID do paciente** não é criado pelo portal. É definido no momento do exame:

1. **Recepção / sistema da clínica** atribui o ID (prontuário, CPF só dígitos, código interno).
2. **Modalidade** envia o exame com esse ID nos metadados DICOM.
3. **Servidor de imagens** indexa o paciente.
4. **Recepção informa** ID + data de nascimento ao paciente para o portal.

Listar IDs existentes (ambiente de desenvolvimento):

```bash
./ohif-viewer/scripts/list-patient-ids.sh
```

---

## 8. Implantação e operação

### 8.1 Desenvolvimento

```bash
cd ohif-viewer
cp .env.example .env
# Editar PORTAL_JWT_SECRET
docker compose up --build -d
```

### 8.2 Produção

```bash
cd ohif-viewer
cp .env.example .env
# Definir segredos fortes, COOKIE_SECURE=true
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

Colocar **TLS** (HTTPS) na frente do gateway (proxy reverso ou certificado no balanceador). Sem HTTPS, definir `COOKIE_SECURE=false` apenas em laboratório.

### 8.3 Estrutura de diretórios

```
lex-pacs/
├── ohif-viewer/          # Gateway, visualizador, servidor de imagens
│   ├── docker-compose.yml
│   ├── docker-compose.prod.yml
│   ├── nginx/gateway.conf
│   ├── orthanc/orthanc.json
│   └── scripts/
└── lex-pacs-portal/      # Portal do paciente
    ├── app/
    └── static/
```

### 8.4 Volumes persistentes

- `orthanc-data`: banco de arquivos e índice do servidor de imagens (cresce com o volume de exames).

---

## 9. Auditoria de segurança

Legenda: **C** crítico · **A** alto · **M** médio · **B** baixo

### 9.1 Achados críticos e altos

| ID | Sev. | Problema | Mitigação |
|----|------|----------|-----------|
| S1 | **C** | Servidor de imagens sem autenticação própria; API 8042 exposta em dev | `docker-compose.prod.yml` remove bind da 8042; firewall; futuro: auth no servidor |
| S2 | **C** | Credenciais clínicas padrão documentadas | Rotacionar senha; não versionar `.htpasswd` real |
| S3 | **A** | `PORTAL_JWT_SECRET` padrão fraco | Obrigar segredo forte no `.env` antes de produção |
| S4 | **A** | Login paciente = ID + nascimento (conhecimento parcial) | Aceitável para portal; reforçar com SMS/OTP em etapa futura |
| S5 | **A** | JWT do portal em `localStorage` (risco XSS) | CSP rigorosa; sanitização; evitar scripts de terceiros |

### 9.2 Achados médios (parcialmente tratados)

| ID | Sev. | Problema | Status |
|----|------|----------|--------|
| S6 | **M** | Endpoint de validação de cookie acessível publicamente | **Corrigido:** bloqueio 404 no gateway |
| S7 | **M** | Cookie sem `Secure` em HTTP | **Corrigido:** `COOKIE_SECURE` configurável |
| S8 | **M** | Swagger/OpenAPI exposto | **Corrigido:** `docs_url=None` |
| S9 | **M** | Health vazava nome do backend | **Corrigido:** campo `storage` genérico |
| S10 | **M** | Sem rate limit no login | **Corrigido:** nginx `limit_req` + API 429 |
| S11 | **M** | Sem CSP/HSTS completos | **Corrigido:** CSP no gateway; HSTS quando `X-Forwarded-Proto: https` |

### 9.3 Modelo de autorização do viewer (pontos fortes)

- Cookie de viewer amarrado ao `study_uid` no JWT.
- `viewer_token_matches_uri` valida UID na query ou path DICOMweb.
- Assets estáticos `/viewer/*` liberados apenas com token viewer válido.
- Worklist `/viewer/` sem UID na URL → paciente recebe **401**.

### 9.4 Recomendações adicionais

1. Autenticação clínica via SSO (Keycloak) — etapa 7 do roadmap.
2. PostgreSQL para índice — etapa 3.
3. Backup automático — etapa 5.
4. Auditoria de acesso (logs centralizados).
5. Penetration test antes de go-live com dados reais.

---

## 10. Auditoria de performance

| ID | Área | Observação | Recomendação |
|----|------|------------|--------------|
| P1 | Build visualizador | Monorepo completo no Docker | `.dockerignore`; cache de camadas |
| P2 | Imagens DICOM | `client_max_body_size 2048M` | Adequado para CT; monitorar disco |
| P3 | Timeouts | 300s em proxy DICOMweb | Adequado para séries grandes |
| P4 | `auth_request` | Chamada ao portal a cada request de imagem | Aceitável; considerar cache curto no futuro |
| P5 | Lazy load | `enableStudyLazyLoad: true` | Positivo |
| P6 | Web workers | `maxNumberOfWebWorkers: 3` | Ajustar conforme CPUs do cliente |
| P7 | Bundle inicial | WASM/codecs volumosos | CDN ou HTTP/2; compressão gzip ativa |
| P8 | `KeepAliveTimeout: 1` no servidor de imagens | Reconexões frequentes | Avaliar aumento para 30s em produção |
| P9 | Volume de dados | Sem política de retenção | Definir arquivamento/backup — etapa 5 |

---

## 11. White-label e superfícies expostas

### 11.1 Superfícies revisadas (marca LEX PACS)

| Superfície | Status |
|------------|--------|
| Título da aba do visualizador | **LEX PACS** |
| `manifest.json` (PWA) | **LEX PACS** |
| Meta tags HTML | **LEX PACS** |
| Modal "Sobre" | **LEX PACS** (sem link para repositórios) |
| Spinner de carregamento | Logo/spinner LEX (sem marca de terceiros) |
| Portal — título e textos | **LEX PACS** |
| Nome da fonte de dados em erros | **LEX PACS** |
| Health API | Campo genérico `storage` |
| Dialog investigacional | Desabilitado (`never`) |
| Modal fallback GPU/CPU | Desabilitado |
| Erro global — link externo | Removido; botão "Fechar" |

### 11.2 Itens que ainda podem aparecer em inspeção avançada

| Item | Risco | Nota |
|------|-------|------|
| Nomes de arquivos JS no bundle (`app.bundle.*.js`) | Baixo | Não visível ao usuário comum |
| Strings em bundles minificados | Baixo | Requer DevTools |
| Favicons padrão em `/assets/` | Médio | Substituir por ícones LEX PACS |
| Header `Server` do gateway | Baixo | `server_tokens off` reduz detalhe |
| Pacote `ImplementationVersionName` em requisições DICOMweb | Baixo | Visível só em tráfego de rede |

### 11.3 Credenciais e textos do gateway

- Realm HTTP Basic: `LEX PACS Clinica` — adequado à marca.

---

## 12. Checklist de produção

### Segurança

- [ ] `PORTAL_JWT_SECRET` com 32+ caracteres aleatórios
- [ ] Senha clínica forte; `.htpasswd` fora do repositório
- [ ] `docker-compose.prod.yml` ativo (sem porta 8042)
- [ ] Firewall: apenas 3000 (HTTPS) e 4242 (DICOM) necessários
- [ ] HTTPS com `COOKIE_SECURE=true`
- [ ] `PORTAL_FALLBACK_CODE` vazio ou muito restrito
- [ ] Backup e restore testados

### Marca e UX

- [ ] Hard refresh no visualizador após deploy
- [ ] Título da aba = LEX PACS
- [ ] Portal sem referências técnicas a padrões ou ferramentas
- [ ] Favicons personalizados (opcional recomendado)

### Operação

- [ ] `docker compose ps` — todos os containers healthy
- [ ] Teste clínico: `/viewer/` com credenciais
- [ ] Teste paciente: login + abrir exame + imagens carregam
- [ ] Teste negativo: `/viewer/` sem auth → 401
- [ ] Teste negativo: paciente não acessa worklist

---

## 13. Roadmap de etapas

O plano completo de produto, priorização, laudos, backup e upgrade está em **[ROADMAP.md](./ROADMAP.md)**.

Resumo:

| Etapa | Entrega | Status |
|-------|---------|--------|
| 1–2 | Portal + gateway + auth | Concluída |
| 2c | AE Title na UI | Concluída |
| 9–11 | Laudo (texto, PDF, assinatura) | MVP concluído |
| 3–8, 12–15 | Ver ROADMAP.md | Pendente |

---

## 14. Anexo técnico interno

> **Uso restrito à equipe de desenvolvimento.** Não distribuir a clientes finais.

### Stack interna (referência para manutenção)

| Camada | Tecnologia interna |
|--------|-------------------|
| Visualizador | Fork do viewer web DICOM v3 |
| Servidor de imagens | Servidor DICOM + plugin DICOMweb |
| Portal API | Framework Python assíncrono |
| Gateway | Proxy reverso |
| Orquestração | Containers Docker Compose |

### Arquivos-chave

| Arquivo | Função |
|---------|--------|
| `ohif-viewer/nginx/gateway.conf` | Roteamento e autenticação |
| `ohif-viewer/orthanc/orthanc.json` | Servidor de imagens |
| `ohif-viewer/platform/app/public/config/default.js` | Config do visualizador |
| `lex-pacs-portal/app/main.py` | API do portal |
| `lex-pacs-portal/app/auth.py` | JWT e validação de cookie |

### Comandos úteis

```bash
# Logs
docker compose -f ohif-viewer/docker-compose.yml logs -f gateway patient-portal ohif

# Reiniciar após alteração de branding
docker compose -f ohif-viewer/docker-compose.yml up --build -d ohif patient-portal
docker compose -f ohif-viewer/docker-compose.yml restart gateway
```

---

*Documento gerado para o projeto LEX PACS. Para dúvidas de implantação, consulte a equipe responsável pelo ambiente.*
