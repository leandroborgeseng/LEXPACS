/**
 * i18n leve para páginas estáticas do portal (vanilla JS).
 * Compartilha chave localStorage i18nextLng com o viewer OHIF.
 */
(function (global) {
  const STORAGE_KEY = 'i18nextLng';
  const SUPPORTED = ['pt-BR', 'en-US', 'es'];
  const DEFAULT_LANG = 'pt-BR';

  const bundles = {};
  let lang = DEFAULT_LANG;

  function resolveLanguage() {
    const params = new URLSearchParams(window.location.search);
    const queryLang = params.get('lng');
    if (queryLang && SUPPORTED.includes(queryLang)) {
      return queryLang;
    }
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored && SUPPORTED.includes(stored)) {
        return stored;
      }
    } catch {
      /* ignore */
    }
    const nav = (navigator.language || '').toLowerCase();
    if (nav.startsWith('pt')) {
      return 'pt-BR';
    }
    if (nav.startsWith('es')) {
      return 'es';
    }
    return 'en-US';
  }

  function getNested(obj, key) {
    return key.split('.').reduce((acc, part) => (acc && acc[part] !== undefined ? acc[part] : undefined), obj);
  }

  function interpolate(template, params) {
    if (!params) {
      return template;
    }
    return template.replace(/\{\{(\w+)\}\}/g, (_, name) =>
      params[name] !== undefined && params[name] !== null ? String(params[name]) : ''
    );
  }

  function t(key, nsOrParams, maybeParams) {
    let ns = 'Portal';
    let params = maybeParams;
    if (typeof nsOrParams === 'string' && bundles[nsOrParams]) {
      ns = nsOrParams;
    } else if (typeof nsOrParams === 'object') {
      params = nsOrParams;
    }
    const value = getNested(bundles[ns], key);
    if (typeof value !== 'string') {
      return key;
    }
    return interpolate(value, params);
  }

  function applyDocument() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      const ns = el.getAttribute('data-i18n-ns') || 'Portal';
      if (key) {
        el.textContent = t(key, ns);
      }
    });
    document.querySelectorAll('[data-i18n-html]').forEach(el => {
      const key = el.getAttribute('data-i18n-html');
      const ns = el.getAttribute('data-i18n-ns') || 'Portal';
      if (key) {
        el.innerHTML = t(key, ns);
      }
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const key = el.getAttribute('data-i18n-placeholder');
      const ns = el.getAttribute('data-i18n-ns') || 'Portal';
      if (key && 'placeholder' in el) {
        el.placeholder = t(key, ns);
      }
    });
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
      const key = el.getAttribute('data-i18n-title');
      const ns = el.getAttribute('data-i18n-ns') || 'Portal';
      if (key) {
        el.title = t(key, ns);
      }
    });
    const titleKey = document.documentElement.getAttribute('data-i18n-title-key');
    if (titleKey) {
      const titleNs = document.documentElement.getAttribute('data-i18n-title-ns') || 'Portal';
      document.title = t(titleKey, titleNs);
    }
    document.documentElement.lang = lang;
  }

  async function init(namespaces) {
    lang = resolveLanguage();
    const list = namespaces && namespaces.length ? namespaces : ['Portal'];
    await Promise.all(
      list.map(async ns => {
        const response = await fetch(`/static/locales/${lang}/${ns}.json`);
        if (!response.ok) {
          throw new Error(`Locale ${lang}/${ns}.json not found`);
        }
        bundles[ns] = await response.json();
      })
    );
    applyDocument();
    return lang;
  }

  function getLanguage() {
    return lang;
  }

  function formatDate(value) {
    if (!value || value.length !== 8) {
      return value || '—';
    }
    const iso = `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
    const parsed = new Date(iso);
    if (Number.isNaN(parsed.getTime())) {
      return value;
    }
    return parsed.toLocaleDateString(lang);
  }

  global.LexI18n = {
    init,
    t,
    applyDocument,
    getLanguage,
    formatDate,
    SUPPORTED,
  };
})(window);
