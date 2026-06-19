import React from 'react';
import { Moon, Sun } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '../Button';
import { useLexTheme } from '../../contexts/LexThemeContext';

type LexThemeToggleProps = {
  className?: string;
  size?: 'default' | 'sm' | 'lg' | 'icon';
};

export function LexThemeToggle({ className, size = 'icon' }: LexThemeToggleProps) {
  const { theme, toggleTheme } = useLexTheme();
  const { t } = useTranslation('LexPacs');

  const isDark = theme === 'dark';
  const label = isDark ? t('theme.switchToLight') : t('theme.switchToDark');

  return (
    <Button
      type="button"
      variant="ghost"
      size={size}
      className={className}
      aria-label={label}
      title={label}
      onClick={toggleTheme}
    >
      {isDark ? (
        <Sun className="text-primary h-4 w-4" aria-hidden="true" />
      ) : (
        <Moon className="text-primary h-4 w-4" aria-hidden="true" />
      )}
    </Button>
  );
}

export default LexThemeToggle;
