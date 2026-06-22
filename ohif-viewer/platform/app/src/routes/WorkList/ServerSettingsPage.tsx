import React, { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { PacsSettingsModal } from './PacsSettingsModal';

export default function ServerSettingsPage() {
  const { t } = useTranslation('LexPacs');

  useEffect(() => {
    const previousTitle = document.title;
    document.title = t('workList.settings.modalTitle');
    return () => {
      document.title = previousTitle;
    };
  }, [t]);

  return (
    <div className="bg-muted text-foreground flex h-screen flex-col p-3 sm:p-5">
      <header className="mb-3 flex shrink-0 items-center justify-between gap-3">
        <h1 className="text-primary text-lg font-semibold">{t('workList.settings.modalTitle')}</h1>
      </header>
      <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <PacsSettingsModal mode="page" />
      </main>
    </div>
  );
}
