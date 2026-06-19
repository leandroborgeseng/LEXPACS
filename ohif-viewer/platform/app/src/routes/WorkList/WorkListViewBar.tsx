import React, { useCallback, useEffect, useMemo, useState } from 'react';
import type { ColumnFiltersState } from '@tanstack/react-table';
import { useTranslation } from 'react-i18next';
import { Button, COLUMN_IDS } from '@ohif/ui-next';

const API_BASE = '/clinica-api/admin/pacs';

export type WorklistView = {
  id: string;
  label: string;
  modalities: string[];
  description?: string;
  station_aet?: string;
};

type WorkListViewBarProps = {
  activeView: string;
  onViewChange: (viewId: string, filters: ColumnFiltersState) => void;
};

export function WorkListViewBar({ activeView, onViewChange }: WorkListViewBarProps) {
  const { t } = useTranslation('LexPacs');
  const [views, setViews] = useState<WorklistView[]>([]);

  const fallbackViews = useMemo<WorklistView[]>(
    () => [
      { id: 'all', label: t('workList.views.all'), modalities: [] },
      {
        id: 'rx-sala-1',
        label: t('workList.views.rxSala1'),
        modalities: ['CR', 'DX'],
        description: 'sala 1',
      },
      {
        id: 'rx-sala-2',
        label: t('workList.views.rxSala2'),
        modalities: ['CR', 'DX'],
        description: 'sala 2',
      },
      { id: 'ct', label: 'CT', modalities: ['CT'] },
      { id: 'mr', label: 'MR', modalities: ['MR'] },
      { id: 'us', label: 'US', modalities: ['US'] },
    ],
    [t]
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(`${API_BASE}/worklist-views`, { credentials: 'include' });
        const data = await response.json().catch(() => ({}));
        if (!cancelled && response.ok && Array.isArray(data.views) && data.views.length) {
          setViews(data.views);
        } else if (!cancelled) {
          setViews(fallbackViews);
        }
      } catch {
        if (!cancelled) {
          setViews(fallbackViews);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [fallbackViews]);

  const applyView = useCallback(
    (view: WorklistView) => {
      onViewChange(view.id, view.id === 'all' ? [] : filtersFromView(view));
    },
    [onViewChange]
  );

  return (
    <div className="flex flex-wrap items-center gap-2 px-4 py-2">
      <span className="text-muted-foreground text-xs uppercase tracking-wide">
        {t('workList.viewLabel')}
      </span>
      {views.map(view => (
        <Button
          key={view.id}
          size="sm"
          variant={activeView === view.id ? 'default' : 'ghost'}
          className="h-8"
          onClick={() => applyView(view)}
        >
          {view.label}
        </Button>
      ))}
    </div>
  );
}

export function filtersFromView(view: WorklistView): ColumnFiltersState {
  const filters: ColumnFiltersState = [];
  if (view.modalities?.length) {
    filters.push({ id: COLUMN_IDS.MODALITIES, value: view.modalities });
  }
  if (view.description) {
    filters.push({ id: COLUMN_IDS.DESCRIPTION, value: view.description });
  }
  return filters;
}

export default WorkListViewBar;
