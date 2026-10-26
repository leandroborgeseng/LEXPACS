const API = '/clinica-api/admin/users';
const LABELS = { admin: 'Administrador', medico: 'Médico', tecnico: 'Técnico', recepcao: 'Recepção', paciente: 'Paciente' };
const uErr = document.getElementById('u-error');
const uOk = document.getElementById('u-ok');

function msg(el, text) {
  el.textContent = text;
  el.classList.remove('hidden');
}

function cell(text) {
  const td = document.createElement('td');
  td.textContent = text;
  return td;
}

async function call(url, options = {}) {
  const r = await fetch(url, { credentials: 'include', headers: { 'Content-Type': 'application/json' }, ...options });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `Erro ${r.status}`);
  return data;
}

async function load() {
  const tbody = document.querySelector('#u-table tbody');
  tbody.replaceChildren();
  let users = [];
  try {
    users = await call(API);
  } catch (e) {
    msg(uErr, e.message);
    return;
  }
  for (const u of users) {
    const tr = document.createElement('tr');
    const state = !u.active ? 'Inativo' : u.locked ? 'Bloqueado' : u.must_change_password ? 'Troca de senha pendente' : 'Ativo';
    tr.append(cell(u.username), cell(u.full_name), cell(LABELS[u.profile] || u.profile), cell(state));
    const td = document.createElement('td');
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'secondary-btn';
    btn.textContent = u.active ? 'Inativar' : 'Reativar';
    btn.addEventListener('click', async () => {
      try {
        await call(`${API}/${encodeURIComponent(u.username)}/${u.active ? 'deactivate' : 'activate'}`, { method: 'POST' });
        await load();
      } catch (e) {
        msg(uErr, e.message);
      }
    });
    td.append(btn);
    tr.append(td);
    tbody.append(tr);
  }
}

document.getElementById('user-form').addEventListener('submit', async event => {
  event.preventDefault();
  uErr.classList.add('hidden');
  uOk.classList.add('hidden');
  const body = {
    username: document.getElementById('u-username').value.trim().toLowerCase(),
    full_name: document.getElementById('u-fullname').value.trim(),
    profile: document.getElementById('u-profile').value,
    password: document.getElementById('u-password').value,
  };
  try {
    await call(API, { method: 'POST', body: JSON.stringify(body) });
    msg(uOk, `Usuário ${body.username} cadastrado. Ele deverá trocar a senha no primeiro acesso.`);
    event.target.reset();
    await load();
  } catch (e) {
    msg(uErr, e.message);
  }
});

load();
