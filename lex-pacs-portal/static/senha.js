const pwForm = document.getElementById('pw-form');
const pwError = document.getElementById('pw-error');

function pwShow(msg) {
  pwError.textContent = msg;
  pwError.classList.remove('hidden');
}

pwForm.addEventListener('submit', async event => {
  event.preventDefault();
  pwError.classList.add('hidden');
  const current = document.getElementById('current').value;
  const n1 = document.getElementById('new1').value;
  const n2 = document.getElementById('new2').value;
  if (n1.length < 10) return pwShow('A nova senha precisa ter pelo menos 10 caracteres.');
  if (n1 !== n2) return pwShow('A confirmação não confere com a nova senha.');
  try {
    const r = await fetch('/clinica-api/auth/clinical/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ current_password: current, new_password: n1 }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) return pwShow(data.detail || 'Não foi possível trocar a senha.');
    window.location.href = '/viewer/';
  } catch {
    pwShow('Falha de conexão. Tente novamente.');
  }
});
