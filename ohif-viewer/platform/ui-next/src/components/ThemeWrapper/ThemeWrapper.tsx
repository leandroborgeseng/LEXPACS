import React from 'react';
import '../../tailwind.css';
import '../../assets/styles.css';
import { LexThemeProvider } from '../../contexts/LexThemeContext';

export function ThemeWrapper({ children }: { children: React.ReactNode }) {
  return <LexThemeProvider>{children}</LexThemeProvider>;
}
