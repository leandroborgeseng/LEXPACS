const form = document.getElementById('login-form');
const errorEl = document.getElementById('login-error');
const submitBtn = document.getElementById('login-btn');
const oidcSection = document.getElementById('oidc-section');
const oidcBtn = document.getElementById('oidc-btn');
const localDevHint = document.getElementById('local-dev-hint');
const loginHint = document.getElementById('login-hint');

function t(key) {
  return LexI18n.t(key, 'ClinicalLogin');
}

function safeNextPath() {
  const params = new URLSearchParams(window.location.search);
  const next = params.get('next') || '/viewer/';
  if (!next.startsWith('/') || next.startsWith('//')) {
    return '/viewer/';
  }
  return next;
}

function showError(message) {
  errorEl.textContent = message;
  errorEl.classList.remove('hidden');
}

async function loadAuthConfig() {
  const params = new URLSearchParams(window.location.search);
  const urlError = params.get('error');
  if (urlError) {
    showError(t('errors.keycloakFailed'));
  }

  try {
    const response = await fetch('/clinica-api/auth/clinical/config');
    const cfg = await response.json().catch(() => ({}));
    if (cfg.enabled) {
      oidcSection.classList.remove('hidden');
      oidcBtn.addEventListener('click', () => {
        const next = encodeURIComponent(safeNextPath());
        window.location.href = `/clinica-api/auth/clinical/oidc/login?next=${next}`;
      });
      loginHint.textContent = t('login.hintKeycloak');
    }
    if (cfg.local_auth_enabled) {
      localDevHint.classList.remove('hidden');
    } else {
      loginHint.textContent = t('login.hintPasswordOnly');
    }
  } catch {
    /* config opcional */
  }
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  errorEl.classList.add('hidden');
  submitBtn.disabled = true;
  const submitLabel = submitBtn.textContent;
  submitBtn.textContent = t('login.submitting');

  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value;

  try {
    const response = await fetch('/clinica-api/auth/clinical/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ username, password, next: safeNextPath() }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      showError(data.detail || t('errors.invalidCredentials'));
      return;
    }
    if (data.access_token) {
      try {
        sessionStorage.setItem('lex_clinical_token', data.access_token);
      } catch {
        /* ignore */
      }
    }
    window.location.href = data.redirect_url || safeNextPath();
  } catch {
    showError(t('errors.connection'));
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = submitLabel;
  }
});

function updateThemeToggleLabel() {
  const theme = document.documentElement.getAttribute('data-theme') || 'dark';
  const label =
    theme === 'dark'
      ? LexI18n.t('theme.switchToLight', 'ClinicalLogin')
      : LexI18n.t('theme.switchToDark', 'ClinicalLogin');
  document.querySelectorAll('[data-theme-toggle]').forEach(btn => {
    btn.setAttribute('aria-label', label);
    btn.setAttribute('title', label);
  });
}

(async function bootstrap() {
  LexTheme.init();
  LexTheme.bindToggleButtons();
  await LexI18n.init(['ClinicalLogin']);
  updateThemeToggleLabel();
  document.querySelectorAll('[data-theme-toggle]').forEach(btn => {
    btn.addEventListener('click', () => setTimeout(updateThemeToggleLabel, 0));
  });
  await loadAuthConfig();
})();
