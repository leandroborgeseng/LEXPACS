export type LexTheme = 'light' | 'dark';

export const LEX_THEME_STORAGE_KEY = 'lex-theme';

export function readStoredTheme(): LexTheme {
  if (typeof window === 'undefined') {
    return 'dark';
  }
  try {
    const stored = localStorage.getItem(LEX_THEME_STORAGE_KEY);
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

export function applyLexTheme(theme: LexTheme): void {
  if (typeof document === 'undefined') {
    return;
  }
  document.documentElement.setAttribute('data-theme', theme);
  try {
    localStorage.setItem(LEX_THEME_STORAGE_KEY, theme);
  } catch {
    /* ignore */
  }
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) {
    meta.setAttribute('content', theme === 'light' ? '#f4f4f5' : '#0f0f0f');
  }
}
