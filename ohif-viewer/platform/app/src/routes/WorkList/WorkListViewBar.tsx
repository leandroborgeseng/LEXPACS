import React from 'react';
import type { ColumnFiltersState } from '@tanstack/react-table';
import {
  Button,
  COLUMN_IDS,
  LEX_DATE_VIEWS,
  LEX_WHOLE_ARCHIVE_MESSAGE,
  lexDateRange,
} from '@ohif/ui-next';

type WorkListViewBarProps = {
  activeView: string;
  onViewChange: (viewId: string) => void;
  /** LP19: com termo digitado a busca cobre todo o acervo e os botões de data ficam inativos. */
  wholeArchive?: boolean;
  /** UXE4: no erro do índice os botões também ficam inativos. */
  disabled?: boolean;
};

/** LP19: Hoje / Esta semana / Semana passada (sem rótulo de grupo, sem abas por sala/modalidade). */
export function WorkListViewBar({
  activeView,
  onViewChange,
  wholeArchive = false,
  disabled = false,
}: WorkListViewBarProps) {
  const inactive = wholeArchive || disabled;
  return (
    <div
      className="flex flex-wrap items-center gap-2 px-4 py-2"
      role="group"
      aria-label="Período"
    >
      {LEX_DATE_VIEWS.map(view => (
        <Button
          key={view.id}
          size="sm"
          variant={activeView === view.id && !wholeArchive ? 'default' : 'ghost'}
          className="h-8"
          disabled={inactive}
          aria-pressed={activeView === view.id && !wholeArchive}
          onClick={() => onViewChange(view.id)}
        >
          {view.label}
        </Button>
      ))}
      {wholeArchive ? (
        <span
          role="status"
          aria-live="polite"
          data-testid="lex-whole-archive"
          className="text-primary text-sm"
        >
          {LEX_WHOLE_ARCHIVE_MESSAGE}
        </span>
      ) : null}
    </div>
  );
}

/** Troca só o filtro de data pelo intervalo da visão; mantém os demais filtros. */
export function filtersWithDateView(
  filters: ColumnFiltersState,
  viewId: string,
  now = new Date()
): ColumnFiltersState {
  return [
    ...filters.filter(f => f.id !== COLUMN_IDS.STUDY_DATE_TIME),
    { id: COLUMN_IDS.STUDY_DATE_TIME, value: lexDateRange(viewId, now) },
  ];
}

export default WorkListViewBar;
