import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import {
  applyLexTheme,
  readStoredTheme,
  type LexTheme,
} from './lexTheme';

type LexThemeContextValue = {
  theme: LexTheme;
  setTheme: (theme: LexTheme) => void;
  toggleTheme: () => void;
};

const LexThemeContext = createContext<LexThemeContextValue | null>(null);

export function LexThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<LexTheme>(() => readStoredTheme());

  const setTheme = useCallback((next: LexTheme) => {
    setThemeState(next);
    applyLexTheme(next);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(theme === 'dark' ? 'light' : 'dark');
  }, [setTheme, theme]);

  useEffect(() => {
    applyLexTheme(theme);
  }, [theme]);

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key !== 'lex-theme' || !event.newValue) {
        return;
      }
      if (event.newValue === 'light' || event.newValue === 'dark') {
        setThemeState(event.newValue);
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const value = useMemo(
    () => ({ theme, setTheme, toggleTheme }),
    [theme, setTheme, toggleTheme]
  );

  return <LexThemeContext.Provider value={value}>{children}</LexThemeContext.Provider>;
}

export function useLexTheme(): LexThemeContextValue {
  const ctx = useContext(LexThemeContext);
  if (!ctx) {
    throw new Error('useLexTheme must be used within LexThemeProvider');
  }
  return ctx;
}
