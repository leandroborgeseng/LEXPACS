# Deploy automático: GitHub → Coolify

## Visão geral

1. **Push na `main`** no GitHub dispara o workflow [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml).
2. O workflow faz **POST** no webhook de deploy do Coolify.
3. O Coolify **reconstrói e reinicia** o stack (conforme configurado no recurso).

O código já está no repositório: `https://github.com/leandroborgeseng/LEXPACS`

## 1. Webhook no Coolify

No painel do Coolify, no recurso **Docker Compose** do LEX PACS:

1. Abra **Webhooks** / **Deploy Webhook** (nome pode variar conforme versão).
2. Gere ou copie a **URL do webhook** de deploy.
3. Se houver token de API, guarde para o secret opcional.

## 2. Secrets no GitHub

Repositório → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Secret | Obrigatório | Descrição |
|--------|-------------|-----------|
| `COOLIFY_WEBHOOK_URL` | Sim | URL completa do webhook de deploy do Coolify |
| `COOLIFY_TOKEN` | Não | Bearer token, se o Coolify exigir no header `Authorization` |

## 3. Coolify alinhado ao repositório

- **Compose file:** `docker-compose.coolify.yml` (e overrides locais/TLS conforme [COOLIFY.md](./COOLIFY.md)).
- **Branch:** `main`
- **Variáveis de ambiente:** `.env.coolify` no Coolify (não commitar segredos). Modelo: [`.env.coolify.example`](../.env.coolify.example).
- **Build:** imagens `lex-pacs/viewer` e `lex-pacs/portal` são construídas no deploy; após mudanças só no viewer, o rebuild do stack no Coolify é suficiente.

## 4. Testar

1. Commit na `main` (ou **Actions** → **Deploy Coolify** → **Run workflow**).
2. Em **Actions**, confirme job verde.
3. No Coolify, confira novo deployment em andamento.
4. Valide: `https://seu-dominio/viewer/` e login clínico.

## 5. Push a partir desta máquina

Se `git push` falhar com *Permission denied (publickey)*:

```bash
# Opção A — SSH (chave em https://github.com/settings/keys)
git remote set-url origin git@github.com:leandroborgeseng/LEXPACS.git
ssh -T git@github.com
git push origin main

# Opção B — GitHub CLI
sudo apt install -y gh
gh auth login
git push origin main
```

## Referências

- [COOLIFY.md](./COOLIFY.md) — stack e domínio
- [TLS-E-DOMINIO.md](./TLS-E-DOMINIO.md) — HTTPS em VPS
