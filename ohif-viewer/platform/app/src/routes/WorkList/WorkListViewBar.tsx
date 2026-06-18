import React, { useCallback, useEffect, useState } from 'react';
import type { ColumnFiltersState } from '@tanstack/react-table';
import { Button, COLUMN_IDS } from '@ohif/ui-next';

const API_BASE = '/clinica-api/admin/pacs';

export type WorklistView = {
  id: string;
  label: string;
  modalities: string[];
  description?: string;
  station_aet?: string;
};

const FALLBACK_VIEWS: WorklistView[] = [
  { id: 'all', label: 'Todos', modalities: [] },
  { id: 'rx-sala-1', label: 'RX Sala 1', modalities: ['CR', 'DX'], description: 'sala 1' },
  { id: 'rx-sala-2', label: 'RX Sala 2', modalities: ['CR', 'DX'], description: 'sala 2' },
  { id: 'ct', label: 'CT', modalities: ['CT'] },
  { id: 'mr', label: 'MR', modalities: ['MR'] },
  { id: 'us', label: 'US', modalities: ['US'] },
];

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

type WorkListViewBarProps = {
  activeView: string;
  onViewChange: (viewId: string, filters: ColumnFiltersState) => void;
};

export function WorkListViewBar({ activeView, onViewChange }: WorkListViewBarProps) {
  const [views, setViews] = useState<WorklistView[]>(FALLBACK_VIEWS);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(`${API_BASE}/worklist-views`, { credentials: 'include' });
        const data = await response.json().catch(() => ({}));
        if (!cancelled && response.ok && Array.isArray(data.views) && data.views.length) {
          setViews(data.views);
        }
      } catch {
        /* fallback */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const applyView = useCallback(
    (view: WorklistView) => {
      onViewChange(view.id, view.id === 'all' ? [] : filtersFromView(view));
    },
    [onViewChange]
  );

  return (
    <div className="flex flex-wrap items-center gap-2 px-4 py-2">
      <span className="text-muted-foreground text-xs uppercase tracking-wide">Visão</span>
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

export default WorkListViewBar;
