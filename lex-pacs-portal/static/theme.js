/**
 * Tema claro/escuro compartilhado com o viewer (localStorage lex-theme).
 */
(function (global) {
  const STORAGE_KEY = 'lex-theme';

  function resolveTheme() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored === 'light' || stored === 'dark') {
        return stored;
      }
    } catch {
      /* ignore */
    }
    if (window.matchMedia('(prefers-color-scheme: light)').matches) {
      return 'light';
    }
    return 'dark';
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* ignore */
    }
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute('content', theme === 'light' ? '#f4f4f5' : '#0f0f0f');
    }
    document.querySelectorAll('[data-theme-toggle]').forEach(btn => {
      const isDark = theme === 'dark';
      btn.setAttribute('aria-pressed', isDark ? 'false' : 'true');
      btn.setAttribute('data-mode', theme);
    });
  }

  function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    applyTheme(current === 'light' ? 'dark' : 'light');
  }

  function initTheme() {
    applyTheme(resolveTheme());
    window.addEventListener('storage', event => {
      if (event.key === STORAGE_KEY && (event.newValue === 'light' || event.newValue === 'dark')) {
        applyTheme(event.newValue);
      }
    });
  }

  function bindToggleButtons() {
    document.querySelectorAll('[data-theme-toggle]').forEach(btn => {
      btn.addEventListener('click', toggleTheme);
    });
  }

  global.LexTheme = {
    init: initTheme,
    toggle: toggleTheme,
    bindToggleButtons,
    resolveTheme,
  };
})(window);
