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

function t(key, params) {
  return LexI18n.t(key, 'Portal', params);
}

function showError(message) {
  loginError.textContent = message;
  loginError.classList.remove('hidden');
}

function clearError() {
  loginError.textContent = '';
  loginError.classList.add('hidden');
}

function formatPatientName(name) {
  if (!name) {
    return t('studies.defaultPatient');
  }
  return name.replace(/\^/g, ' ');
}

async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers, credentials: 'same-origin' });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || t('errors.generic'));
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
    throw new Error(data.detail || t('errors.openViewer'));
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
      ? t('report.signedBy', {
          name: data.signed_by,
          crm: data.signed_crm ? t('report.signedByCrm', { crm: data.signed_crm }) : '',
        })
      : '';
    reportMeta.textContent = `${studyDescription || t('studies.studyDefault')}${signedLine ? ` · ${signedLine}` : ''}`;
    reportContent.innerHTML = data.content_html || `<p class="hint">${t('report.noText')}</p>`;
    if (data.has_pdf) {
      reportPdfLink.classList.remove('hidden');
      reportPdfAnchor.textContent = data.pdf_filename || t('report.openPdf');
      reportPdfAnchor.onclick = async event => {
        event.preventDefault();
        const pdfResponse = await fetch(`${API_BASE}/studies/${encodeURIComponent(studyUid)}/report/pdf`, {
          headers: { Authorization: `Bearer ${localStorage.getItem(TOKEN_KEY)}` },
          credentials: 'same-origin',
        });
        if (!pdfResponse.ok) {
          reportError.textContent = t('report.pdfError');
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
  patientLabel.textContent = t('studies.patientLabel', {
    name: formatPatientName(data.patient_name),
    id: data.patient_id,
  });
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
      <strong>${study.study_description || t('studies.studyDefault')}</strong>
      <div class="study-meta">${t('studies.date')} ${LexI18n.formatDate(study.study_date)} · ${t('studies.modality')} ${modalities}</div>
      <div class="study-meta">${t('studies.series')} ${study.series_count || 0} · ${t('studies.instances')} ${study.instance_count || 0}</div>
      <div class="study-actions"></div>
    `;
    const actions = item.querySelector('.study-actions');
    if (uid) {
      const viewBtn = document.createElement('button');
      viewBtn.type = 'button';
      viewBtn.textContent = t('studies.viewStudy');
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
        reportBtn.textContent = t('studies.viewReport');
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
  const submitLabel = btn.textContent;
  btn.textContent = t('login.submitting');
  try {
    const payload = {
      patient_id: document.getElementById('patient-id').value.trim(),
      birth_date: document.getElementById('birth-date').value.trim(),
    };
    const accessCode = document.getElementById('access-code').value.trim();
    if (accessCode) {
      payload.access_code = accessCode;
    }

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
    btn.textContent = submitLabel;
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

function updateThemeToggleLabel() {
  const theme = document.documentElement.getAttribute('data-theme') || 'dark';
  const label =
    theme === 'dark'
      ? LexI18n.t('theme.switchToLight', 'Portal')
      : LexI18n.t('theme.switchToDark', 'Portal');
  document.querySelectorAll('[data-theme-toggle]').forEach(btn => {
    btn.setAttribute('aria-label', label);
    btn.setAttribute('title', label);
  });
}

(async function bootstrap() {
  LexTheme.init();
  LexTheme.bindToggleButtons();
  await LexI18n.init(['Portal']);
  updateThemeToggleLabel();
  document.querySelectorAll('[data-theme-toggle]').forEach(btn => {
    btn.addEventListener('click', () => setTimeout(updateThemeToggleLabel, 0));
  });
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
