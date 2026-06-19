# Traduções LEX PACS

Fonte única de strings traduzíveis do produto (viewer OHIF, portal do paciente e login clínico).

## Idiomas suportados

| Código   | Idioma              |
|----------|---------------------|
| `pt-BR`  | Português (Brasil)  |
| `en-US`  | Inglês (EUA)        |
| `es`     | Espanhol            |

## Namespaces

| Arquivo              | Consumidor                          |
|----------------------|-------------------------------------|
| `LexPacs.json`       | Viewer OHIF (componentes LEX)       |
| `Portal.json`        | Portal do paciente (`index.html`)   |
| `ClinicalLogin.json` | Login clínico (`clinica.html`)      |
| `Errors.json`        | Referência de mensagens de API (*)  |

(*) Mensagens do backend FastAPI ainda estão em português; `Errors.json` documenta chaves para migração futura com `Accept-Language`.

## Sincronizar após editar

```bash
./scripts/sync-locales.sh
```

Copia os JSON para:

- `ohif-viewer/platform/i18n/src/locales/{lang}/LexPacs.json` (bundle do viewer)
- `lex-pacs-portal/static/locales/{lang}/` (servidos em `/static/locales/`)

## Uso no viewer (React)

```tsx
import { useTranslation } from 'react-i18next';

const { t, i18n } = useTranslation('LexPacs');
t('report.title');
value.toLocaleString(i18n.language);
```

Idioma: **User Preferences** no viewer, ou `?lng=pt-BR` na URL. Persistido em `localStorage` (`i18nextLng`).

## Uso no portal (vanilla JS)

```html
<h1 data-i18n="login.title" data-i18n-ns="Portal"></h1>
<script src="/static/i18n.js"></script>
<script src="/static/portal.js"></script>
```

```javascript
await LexI18n.init(['Portal']);
LexI18n.t('login.title');
```

Idioma: `?lng=es`, `localStorage.i18nextLng` (compartilhado com o viewer) ou idioma do navegador.

## Adicionar novo texto

1. Edite os três arquivos do namespace em `pt-BR`, `en-US` e `es`.
2. Rode `./scripts/sync-locales.sh`.
3. No viewer: `docker compose build ohif` se alterou `LexPacs.json`.
4. Portal: basta recarregar (JSON estático).

Ver [docs/I18N.md](../docs/I18N.md) para auditoria completa do código.
