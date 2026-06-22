# Rede Docker — LEX PACS

Toda comunicação **entre containers** ocorre na rede interna do Docker Compose (`lex-pacs_default`). Nenhum serviço backend precisa (nem deve) chamar a internet para falar com outro componente do stack.

---

## Matriz de conexões

| Origem | Destino | URL interna | Porta exposta ao host? |
|--------|---------|-------------|------------------------|
| **portal** | Orthanc | `http://server:8042` | Não (8042 só na rede Docker) |
| **portal** | Keycloak (token/JWKS) | `http://auth:8080/auth/realms/lex-pacs` | Não |
| **portal** | PostgreSQL (MWL) | `database:5432` | Não |
| **gateway** | portal | `http://portal:8080` | Opcional `:3000` (dev local) |
| **gateway** | web-viewer | `http://web-viewer:80` | Não |
| **gateway** | server | `http://server:8042` | Não |
| **gateway** | auth | `http://auth:8080` | Não |
| **server** | PostgreSQL | `database:5432` | Não |
| **Navegador** | gateway | `OHIF_VIEWER_URL` (domínio público) | Sim (80/443 ou proxy) |

---

## URLs públicas vs internas

### Só para o navegador (variáveis públicas)

| Variável | Exemplo | Uso |
|----------|---------|-----|
| `OHIF_VIEWER_URL` | `https://pacs.clinica.com` | Redirect URI OIDC, links de retorno |
| `OIDC_PUBLIC_ISSUER_URL` | `https://pacs.clinica.com/auth/realms/lex-pacs` | Login SSO no browser (derivada de `OHIF_VIEWER_URL` se omitida) |
| `KEYCLOAK_PUBLIC_HOSTNAME` | `pacs.clinica.com` | Hostname nos redirects do Keycloak |

### Sempre na rede Docker (não alterar para domínio público)

| Variável | Valor padrão | Quem consome |
|----------|--------------|--------------|
| `ORTHANC_URL` | `http://server:8042` | portal (API Orthanc) |
| `OIDC_ISSUER_URL` | `http://auth:8080/auth/realms/lex-pacs` | portal (token exchange, JWKS, password grant) |

O viewer OHIF usa paths **relativos** (`/dicom-web`, `/wado`) em `default.js` — o browser fala com o gateway, que repassa ao `server` internamente.

---

## Proxy externo (nginx no host)

Cenário comum em desenvolvimento/VPS:

```
Navegador → http://meudominio.com:80 → nginx host → gateway:3000 → containers
```

Nesse caso:

1. `OHIF_VIEWER_URL` deve ser **`http://meudominio.com`** (sem `:3000` se o nginx escuta na 80).
2. `OIDC_PUBLIC_ISSUER_URL` será `http://meudominio.com/auth/realms/lex-pacs`.
3. **Não** mude `OIDC_ISSUER_URL` nem `ORTHANC_URL` — continuam com `auth` e `server`.

Após alterar `.env.coolify`, recrie o portal e o realm Keycloak:

```bash
docker compose -f docker-compose.coolify.yml -f docker-compose.coolify.local.yml \
  --env-file .env.coolify up -d --force-recreate auth-realm-init auth portal
```

---

## Validar conectividade

```bash
chmod +x scripts/check-docker-network.sh
./scripts/check-docker-network.sh

# Se acessa via domínio externo:
GATEWAY_URL=http://meudominio.com ./scripts/check-docker-network.sh
```

O script testa:

- Containers em execução
- `portal` → `server`, `auth`, `database`
- `gateway` → `portal`, `web-viewer`, `server`, `auth`
- Variáveis de ambiente (URLs internas corretas, URL pública alinhada)

---

## Tráfego externo intencional

| Destino | Quando |
|---------|--------|
| Registry Docker (pull de imagens) | Deploy / `docker compose pull` |
| Let's Encrypt | Stack com `docker-compose.tls.yml` + Caddy |
| Navegador do usuário | Acesso clínico/paciente ao domínio |

Erros como `get3DContext` / WebGL ocorrem **no navegador** (GPU/driver), não na rede Docker.

---

## DNS dinâmico no gateway

O `gateway.conf` usa `resolver 127.0.0.11` e variáveis `$lex_upstream_*` para evitar 502 quando containers são recriados e o IP Docker muda. Isso também mantém resolução na rede interna.
