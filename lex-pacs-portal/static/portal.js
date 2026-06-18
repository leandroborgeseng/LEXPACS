const TOKEN_KEY = 'lex_pacs_portal_token';
const API_BASE = '/paciente-api';

const loginView = document.getElementById('login-view');
const studiesView = document.getElementById('studies-view');
const reportView = document.getElementById('report-view');
const loginForm = document.getElementById('login-form');
const loginError = document.getElementById('login-error');
const studiesList = document.getElementById('studies-list');
const studiesEmpty = document.getElementById('studies-empty');
const patientLabel = document.getElementById('patient-label');
const logoutBtn = document.getElementById('logout-btn');
const reportMeta = document.getElementById('report-meta');
const reportContent = document.getElementById('report-content');
const reportPdfLink = document.getElementById('report-pdf-link');
const reportPdfAnchor = document.getElementById('report-pdf-anchor');
const reportError = document.getElementById('report-error');
const reportBackBtn = document.getElementById('report-back-btn');

function showError(message) {
  loginError.textContent = message;
  loginError.classList.remove('hidden');
}

function clearError() {
  loginError.textContent = '';
  loginError.classList.add('hidden');
}

function formatDate(value) {
  if (!value || value.length !== 8) return value || '—';
  return `${value.slice(6, 8)}/${value.slice(4, 6)}/${value.slice(0, 4)}`;
}

function formatPatientName(name) {
  if (!name) return 'Paciente';
  return name.replace(/\^/g, ' ');
}

async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers, credentials: 'same-origin' });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || 'Não foi possível completar a operação.');
  }
  return data;
}

function showLogin() {
  loginView.classList.remove('hidden');
  studiesView.classList.add('hidden');
  reportView.classList.add('hidden');
}

function showStudies() {
  loginView.classList.add('hidden');
  studiesView.classList.remove('hidden');
  reportView.classList.add('hidden');
}

function showReport() {
  loginView.classList.add('hidden');
  studiesView.classList.add('hidden');
  reportView.classList.remove('hidden');
}

async function openViewer(studyUid) {
  const response = await fetch(`${API_BASE}/studies/${encodeURIComponent(studyUid)}/viewer-session`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${localStorage.getItem(TOKEN_KEY)}`,
    },
    credentials: 'same-origin',
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || 'Não foi possível abrir o exame.');
  }
  window.location.href = data.redirect_url;
}

async function openReport(studyUid, studyDescription) {
  reportError.classList.add('hidden');
  reportContent.innerHTML = '';
  reportPdfLink.classList.add('hidden');
  try {
    const data = await api(`/studies/${encodeURIComponent(studyUid)}/report`);
    const signedLine = data.signed_by
      ? `Assinado por ${data.signed_by}${data.signed_crm ? ` — CRM ${data.signed_crm}` : ''}`
      : '';
    reportMeta.textContent = `${studyDescription || 'Exame'}${signedLine ? ` · ${signedLine}` : ''}`;
    reportContent.innerHTML = data.content_html || '<p class="hint">Laudo sem texto — consulte o PDF se disponível.</p>';
    if (data.has_pdf) {
      reportPdfLink.classList.remove('hidden');
      reportPdfAnchor.textContent = data.pdf_filename || 'Abrir PDF do laudo';
      reportPdfAnchor.onclick = async event => {
        event.preventDefault();
        const pdfResponse = await fetch(
          `${API_BASE}/studies/${encodeURIComponent(studyUid)}/report/pdf`,
          {
            headers: { Authorization: `Bearer ${localStorage.getItem(TOKEN_KEY)}` },
            credentials: 'same-origin',
          }
        );
        if (!pdfResponse.ok) {
          reportError.textContent = 'Não foi possível abrir o PDF.';
          reportError.classList.remove('hidden');
          return;
        }
        const blob = await pdfResponse.blob();
        window.open(URL.createObjectURL(blob), '_blank', 'noopener');
      };
    }
    showReport();
  } catch (error) {
    reportError.textContent = error.message;
    reportError.classList.remove('hidden');
    showReport();
  }
}

async function loadStudies() {
  const data = await api('/studies');
  patientLabel.textContent = `${formatPatientName(data.patient_name)} · ID ${data.patient_id}`;
  studiesList.innerHTML = '';

  if (!data.studies?.length) {
    studiesEmpty.classList.remove('hidden');
    return;
  }

  studiesEmpty.classList.add('hidden');
  data.studies.forEach(study => {
    const item = document.createElement('article');
    item.className = 'study-item';
    const modalities = (study.modalities || []).join(', ') || '—';
    const uid = study.study_instance_uid;
    item.innerHTML = `
      <strong>${study.study_description || 'Exame'}</strong>
      <div class="study-meta">Data: ${formatDate(study.study_date)} · Modalidade: ${modalities}</div>
      <div class="study-meta">Séries: ${study.series_count || 0} · Imagens: ${study.instance_count || 0}</div>
      <div class="study-actions"></div>
    `;
    const actions = item.querySelector('.study-actions');
    if (uid) {
      const viewBtn = document.createElement('button');
      viewBtn.type = 'button';
      viewBtn.textContent = 'Visualizar exame';
      viewBtn.addEventListener('click', async () => {
        viewBtn.disabled = true;
        try {
          await openViewer(uid);
        } catch (error) {
          showError(error.message);
          viewBtn.disabled = false;
        }
      });
      actions.appendChild(viewBtn);

      if (study.report_available) {
        const reportBtn = document.createElement('button');
        reportBtn.type = 'button';
        reportBtn.className = 'secondary';
        reportBtn.textContent = 'Ver laudo';
        reportBtn.addEventListener('click', () => openReport(uid, study.study_description));
        actions.appendChild(reportBtn);
      }
    }
    studiesList.appendChild(item);
  });
}

loginForm.addEventListener('submit', async event => {
  event.preventDefault();
  clearError();
  const btn = document.getElementById('login-btn');
  btn.disabled = true;
  try {
    const payload = {
      patient_id: document.getElementById('patient-id').value.trim(),
      birth_date: document.getElementById('birth-date').value.trim(),
    };
    const accessCode = document.getElementById('access-code').value.trim();
    if (accessCode) payload.access_code = accessCode;

    const data = await api('/auth/login', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    localStorage.setItem(TOKEN_KEY, data.access_token);
    await loadStudies();
    showStudies();
  } catch (error) {
    showError(error.message);
  } finally {
    btn.disabled = false;
  }
});

logoutBtn.addEventListener('click', () => {
  localStorage.removeItem(TOKEN_KEY);
  loginForm.reset();
  showLogin();
});

reportBackBtn.addEventListener('click', () => {
  showStudies();
});

(async function bootstrap() {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) {
    showLogin();
    return;
  }
  try {
    await loadStudies();
    showStudies();
  } catch {
    localStorage.removeItem(TOKEN_KEY);
    showLogin();
  }
})();
