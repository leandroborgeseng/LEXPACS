const form = document.getElementById('login-form');
const errorEl = document.getElementById('login-error');
const submitBtn = document.getElementById('login-btn');
const oidcSection = document.getElementById('oidc-section');
const oidcBtn = document.getElementById('oidc-btn');
const localDevHint = document.getElementById('local-dev-hint');
const loginHint = document.getElementById('login-hint');

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
    showError('Login Keycloak cancelado ou falhou. Tente novamente.');
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
      loginHint.textContent = 'Autenticação institucional via Keycloak.';
    }
    if (cfg.local_auth_enabled) {
      localDevHint.classList.remove('hidden');
    } else {
      loginHint.textContent = 'Use o botão Keycloak ou credenciais institucionais.';
    }
  } catch {
    /* config opcional */
  }
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  errorEl.classList.add('hidden');
  submitBtn.disabled = true;
  submitBtn.textContent = 'Entrando…';

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
      showError(data.detail || 'Usuário ou senha incorretos.');
      return;
    }
    window.location.href = data.redirect_url || safeNextPath();
  } catch {
    showError('Não foi possível conectar ao servidor.');
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Acessar worklist';
  }
});

void loadAuthConfig();
