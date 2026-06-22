# Domínio, portas 80/443 e Let's Encrypt

O LEX PACS pode ser publicado de três formas. Escolha **uma** — não combine edge TLS com Coolify Traefik no mesmo host.

---

## Modos de deploy

| Modo | Quem termina TLS | Portas públicas | Domínio |
|------|------------------|-----------------|---------|
| **Desenvolvimento local** | Ninguém (HTTP) | `3000` → gateway | `localhost` |
| **Coolify** | Traefik do Coolify | `80` / `443` | UI Coolify → serviço `gateway` |
| **VPS standalone** | Caddy (`edge`) | `80` / `443` | `.env` → `LEX_PACS_DOMAIN` |

---

## 1. Desenvolvimento local (sem TLS)

```bash
cp .env.coolify.example .env.coolify
```

```env
OHIF_VIEWER_URL=http://localhost:3000
COOKIE_SECURE=false
CLINICAL_LOCAL_AUTH_ENABLED=true
CLINICAL_BOOTSTRAP_USER=clinica
CLINICAL_BOOTSTRAP_PASSWORD=lexclinica2024
```

```bash
docker compose -f docker-compose.coolify.yml \
  -f docker-compose.coolify.local.yml \
  --env-file .env.coolify up -d --build
```

Acesso: http://localhost:3000/clinica/login

---

## 2. Coolify (recomendado em produção)

O Coolify já expõe **80/443** com **Let's Encrypt** via Traefik.

1. Crie o recurso Docker Compose (`docker-compose.coolify.yml`)
2. Atribua **um domínio** ao serviço **`gateway`** (HTTPS ativado)
3. Configure variáveis (não use `docker-compose.tls.yml`):

```env
OHIF_VIEWER_URL=https://pacs.seudominio.com
COOKIE_SECURE=true
KEYCLOAK_SSL_REQUIRED=external
KEYCLOAK_PUBLIC_HOSTNAME=pacs.seudominio.com
OIDC_ENABLED=true
CLINICAL_LOCAL_AUTH_ENABLED=false
```

`LEX_PACS_DOMAIN` e `LETSENCRYPT_EMAIL` **não são necessários** no Coolify — o domínio e o certificado ficam na UI.

Detalhes: [COOLIFY.md](./COOLIFY.md)

---

## 3. VPS standalone (Caddy + Let's Encrypt)

Para servidor próprio **sem** Coolify: o serviço **`edge`** (Caddy) escuta **80/443**, obtém certificado Let's Encrypt e repassa ao `gateway`.

### Pré-requisitos

- DNS **A/AAAA** de `pacs.seudominio.com` → IP do servidor
- Portas **80** e **443** abertas no firewall
- Nenhum outro processo (nginx/apache) ocupando 80/443 neste host

### Configuração (`.env.coolify`)

```env
# ── Domínio e TLS (standalone) ──
LEX_PACS_DOMAIN=pacs.seudominio.com
LETSENCRYPT_EMAIL=admin@seudominio.com

# URL pública — deve ser https:// + mesmo domínio
OHIF_VIEWER_URL=https://pacs.seudominio.com
COOKIE_SECURE=true

KEYCLOAK_SSL_REQUIRED=external
KEYCLOAK_PUBLIC_HOSTNAME=pacs.seudominio.com
KEYCLOAK_PROXY=edge

OIDC_ENABLED=true
CLINICAL_LOCAL_AUTH_ENABLED=false

# … demais segredos (POSTGRES_PASSWORD, OIDC_CLIENT_SECRET, etc.)
```

Valide:

```bash
./scripts/validate-coolify-env.sh
./scripts/validate-coolify-env.sh --tls
```

### Subir stack

```bash
docker compose -f docker-compose.coolify.yml \
  -f docker-compose.tls.yml \
  --env-file .env.coolify up -d --build
```

### Verificação

```bash
curl -fsSI https://pacs.seudominio.com/clinica/login | head
curl -fsS https://pacs.seudominio.com/auth/realms/lex-pacs/.well-known/openid-configuration | head
docker logs edge --tail 30
```

Certificados ficam no volume `caddy-data` (renovação automática).

---

## Variáveis de domínio (referência)

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `LEX_PACS_DOMAIN` | Standalone TLS | FQDN público (sem `https://`) |
| `LETSENCRYPT_EMAIL` | Standalone TLS | E-mail Let's Encrypt |
| `OHIF_VIEWER_URL` | Sempre | URL base (`https://dominio` ou `http://localhost:3000`) |
| `KEYCLOAK_PUBLIC_HOSTNAME` | HTTPS | Mesmo host do domínio (sem path) |
| `COOKIE_SECURE` | Sempre | `true` com HTTPS, `false` só em HTTP local |
| `KEYCLOAK_SSL_REQUIRED` | HTTPS | `external` em produção |

`OIDC_PUBLIC_ISSUER_URL` é derivada automaticamente: `${OHIF_VIEWER_URL}/auth/realms/lex-pacs`.

---

## Nginx no host (alternativa manual)

Se preferir nginx no Ubuntu em vez do container `edge`:

- **Com Coolify:** não use — Traefik já faz o papel
- **Local com gateway em :3000:** `ohif-viewer/nginx/host-reverse-proxy.conf` (só HTTP :80)

Para HTTPS manual no host, use Certbot + proxy para `127.0.0.1:3000` ou integre o `docker-compose.tls.yml` (Caddy) — é o caminho suportado para LE automático.

---

## Troubleshooting TLS

| Sintoma | Causa | Ação |
|---------|-------|------|
| Certificado não emitido | DNS não aponta / porta 80 bloqueada | Conferir `dig +short $DOMAIN` e firewall |
| Redirect OIDC errado | `OHIF_VIEWER_URL` ≠ domínio real | Igualar URL, redeploy |
| Cookie não persiste | `COOKIE_SECURE=true` sem HTTPS | Ativar TLS ou `COOKIE_SECURE=false` (só dev) |
| 502 após deploy | Gateway ainda subindo | Aguardar healthchecks; `docker logs gateway` |
| Conflito porta 80 | nginx/apache no host | Parar serviço ou usar só Caddy (`edge`) |
