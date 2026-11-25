import * as React from 'react';
import { TableRow, TableCell } from '../Table';
import { Input } from '../Input';

import { useDataTable } from './context';

export type FilterRowProps = {
  /** LEX PACS UXE4: desativa todos os filtros da linha (inert: sem foco nem clique). */
  disabled?: boolean;
  excludeColumnIds?: string[];
  renderFilterCell?: (opts: {
    columnId: string;
    value: unknown;
    setValue: (v: unknown) => void;
  }) => React.ReactNode;
};

export function FilterRow<TData>({
  excludeColumnIds = [],
  renderFilterCell,
  disabled = false,
}: FilterRowProps) {
  const { table } = useDataTable<TData>();
  const cols = table.getVisibleLeafColumns();
  return (
    <TableRow
      data-filter-row
      data-disabled={disabled ? 'true' : undefined}
      aria-disabled={disabled || undefined}
      {...(disabled ? ({ inert: '' } as Record<string, string>) : {})}
      className={disabled ? 'pointer-events-none opacity-50 hover:bg-transparent' : 'hover:bg-transparent'}
    >
      {cols.map(col => {
        const id = col.id;
        const value = table.getColumn(id)?.getFilterValue();
        const setValue = (v: unknown) => table.getColumn(id)?.setFilterValue(v);

        if (excludeColumnIds?.includes(id)) {
          return <TableCell key={id} />;
        }

        const customRender = renderFilterCell?.({ columnId: id, value, setValue });

        if (customRender) {
          return <TableCell key={id}>{customRender}</TableCell>;
        }

        // Default cell rendering
        return (
          <TableCell key={id}>
            <Input
              value={(value as string) ?? ''}
              onChange={e => setValue(e.target.value)}
              className="h-7 w-full"
            />
          </TableCell>
        );
      })}
    </TableRow>
  );
}
