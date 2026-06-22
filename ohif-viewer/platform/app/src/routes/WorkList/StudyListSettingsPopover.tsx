import React, { useEffect, useState } from 'react';
import { useNavigate, type NavigateFunction } from 'react-router-dom';
import { useTranslation, type TFunction } from 'react-i18next';

import { useAppConfig } from '@state';
import { useSystem } from '@ohif/core';
import { StudyList, Icons, Button, useModal } from '@ohif/ui-next';
import { routerBasename } from '../../utils/publicUrl';
import { lexClinicalLogout } from './lexClinicalAuth';
import { fetchClinicalProfile, type ClinicalProfile } from './lexClinicalUser';

export type SettingsMenuItem = {
  id: string;
  label: React.ReactNode;
  onClick: () => void;
};

type DefaultItemsContext = {
  t: TFunction;
  navigate: NavigateFunction;
  customizationService: any;
  show: ReturnType<typeof useModal>['show'];
  appConfig: ReturnType<typeof useAppConfig>[0];
};

export function defaultSettingsMenuItems({
  t,
  navigate,
  customizationService,
  show,
  appConfig,
}: DefaultItemsContext): SettingsMenuItem[] {
  const items: SettingsMenuItem[] = [
    {
      id: 'pacsSettings',
      label: t('workList.settings.dicom'),
      onClick: () => {
        const base = routerBasename.replace(/\/$/, '');
        const path = `${base}/server-settings`.replace(/\/{2,}/g, '/');
        const url = `${window.location.origin}${path}`;
        window.open(url, 'lex-pacs-server-settings', 'noopener,noreferrer,width=1280,height=900');
      },
    },
    {
      id: 'about',
      label: t('workList.settings.about'),
      onClick: () => {
        const AboutModal = customizationService.getCustomization('ohif.aboutModal');
        show({
          content: AboutModal,
          title: AboutModal?.title ?? t('AboutModal:About LEX PACS'),
          containerClassName: AboutModal?.containerClassName ?? 'max-w-md',
        });
      },
    },
    {
      id: 'userPreferences',
      label: t('workList.settings.userPreferences'),
      onClick: () => {
        const UserPreferencesModal = customizationService.getCustomization(
          'ohif.userPreferencesModal'
        );
        show({
          content: UserPreferencesModal,
          title: UserPreferencesModal?.title ?? t('UserPreferencesModal:User preferences'),
          containerClassName:
            UserPreferencesModal?.containerClassName ?? 'flex max-w-4xl p-6 flex-col',
        });
      },
    },
  ];

  items.push({
    id: 'logout',
    label: t('workList.settings.logout'),
    onClick: () => {
      void lexClinicalLogout();
    },
  });

  return items;
}

export function StudyListSettingsPopover() {
  // SettingsPopover.Workflow now uses useStudyListWorkflows internally
  const { t } = useTranslation('LexPacs');
  const [appConfig] = useAppConfig();
  const navigate = useNavigate();
  const { servicesManager } = useSystem();
  const { customizationService } = servicesManager.services as any;
  const { show } = useModal();
  const [profile, setProfile] = useState<ClinicalProfile | null>(null);

  useEffect(() => {
    void fetchClinicalProfile().then(setProfile);
  }, []);

  const defaults = defaultSettingsMenuItems({
    t,
    navigate,
    customizationService,
    show,
    appConfig,
  });
  const buildItems = customizationService.getCustomization('workList.settingsMenuItems');
  const items: SettingsMenuItem[] =
    typeof buildItems === 'function'
      ? (() => {
          const result = (
            buildItems as (defaults: SettingsMenuItem[]) => SettingsMenuItem[]
          )(defaults);
          return Array.isArray(result) ? result : defaults;
        })()
      : defaults;

  return (
    <StudyList.SettingsPopover>
      {profile ? (
        <span
          className="text-muted-foreground hidden max-w-[140px] truncate text-[11px] leading-tight sm:inline"
          title={`${profile.username} — ${t(`roles.${profile.permissions.role}`, { defaultValue: profile.permissions.role_label })}`}
        >
          {t(`roles.${profile.permissions.role}`, { defaultValue: profile.permissions.role_label })}
        </span>
      ) : null}
      <StudyList.SettingsPopover.Trigger>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Open settings"
        >
          <Icons.SettingsStudyList
            aria-hidden="true"
            className="text-primary h-4 w-4"
          />
        </Button>
      </StudyList.SettingsPopover.Trigger>
      <StudyList.SettingsPopover.Content>
        <StudyList.SettingsPopover.Workflow />
        <StudyList.SettingsPopover.Divider />
        {items.map(item => (
          <StudyList.SettingsPopover.Item
            key={item.id}
            onClick={item.onClick}
          >
            {item.label}
          </StudyList.SettingsPopover.Item>
        ))}
      </StudyList.SettingsPopover.Content>
    </StudyList.SettingsPopover>
  );
}
