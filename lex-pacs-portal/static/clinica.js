const form = document.getElementById('login-form');
const errorEl = document.getElementById('login-error');
const submitBtn = document.getElementById('login-btn');

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
