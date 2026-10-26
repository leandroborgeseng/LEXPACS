import * as React from 'react';
import { Button } from '../Button';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from '../DropdownMenu';
import { Icons } from '../Icons';
import { useDataTable } from './context';
import { lexPageOf, lexPageRange } from './lexPaginationLabel';

/**
 * Pagination
 * Renders "start-end of total" and ghost chevron buttons for prev/next.
 * Uses the TanStack table instance from DataTable context.
 */
export function Pagination<TData>() {
  const { table } = useDataTable<TData>();
  const { pageIndex, pageSize } = table.getState().pagination ?? { pageIndex: 0, pageSize: 50 };
  const serverPaging = (table.options.meta as { lexServerPaging?: { total: number | null; sortNote?: string | null } } | undefined)
    ?.lexServerPaging;
  if (serverPaging) {
    return (
      <ServerPagination
        table={table}
        pageIndex={pageIndex}
        pageSize={pageSize}
        total={serverPaging.total}
        sortNote={serverPaging.sortNote ?? null}
      />
    );
  }

  const total = table.getFilteredRowModel().rows.length;
  const start = total === 0 ? 0 : pageIndex * pageSize + 1;
  const end = Math.min(total, (pageIndex + 1) * pageSize);

  const canPrev = table.getCanPreviousPage();
  const canNext = table.getCanNextPage();

  return (
    <div className="mr-2 flex items-center gap-0.5">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className="text-primary/80 px-2 text-sm leading-tight"
            aria-label="Rows per page"
          >
            {`${start}-${end} of ${total}`}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          {[25, 50, 100].map(size => (
            <DropdownMenuItem
              key={size}
              onSelect={e => {
                e.preventDefault();
                table.setPageSize(size);
              }}
              className="flex items-center gap-[2px]"
            >
              <Icons.Checked className={`h-6 w-6 ${pageSize === size ? '' : 'invisible'}`} />
              {size} per page
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      <Button
        variant="ghost"
        size="icon"
        aria-label="Previous page"
        onClick={() => table.previousPage()}
        disabled={!canPrev}
        className="ml-1"
      >
        <Icons.ChevronLeft className="h-3 w-3" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        aria-label="Next page"
        onClick={() => table.nextPage()}
        disabled={!canNext}
      >
        <Icons.ChevronRight className="h-3 w-3" />
      </Button>
    </div>
  );
}

/**
 * LEX PACS — paginação no servidor (busca-paginada-esboco.md): "Exibindo 1–50 de N exames",
 * seletor 50/100, "Anterior" | "Página X de Y" | "Próxima". Números em .lex-num (LX6).
 */
function ServerPagination({
  table,
  pageIndex,
  pageSize,
  total,
  sortNote,
}: {
  table: ReturnType<typeof useDataTable>['table'];
  pageIndex: number;
  pageSize: number;
  total: number | null;
  sortNote: string | null;
}) {
  const count = table.getRowModel().rows.length;
  const range = lexPageRange({ pageIndex, pageSize, count, total });
  const pageOf = lexPageOf({ pageIndex, pageSize, total });
  return (
    <nav
      className="mr-2 flex items-center gap-1"
      aria-label="Paginação"
    >
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className="lex-num text-primary/80 px-2 text-sm leading-tight"
            aria-label="Exames por página"
          >
            {range}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          {[50, 100].map(size => (
            <DropdownMenuItem
              key={size}
              onSelect={e => {
                e.preventDefault();
                table.setPagination({ pageIndex: 0, pageSize: size });
              }}
              className="flex items-center gap-[2px]"
            >
              <Icons.Checked className={`h-6 w-6 ${pageSize === size ? '' : 'invisible'}`} />
              <span className="lex-num">{size}</span> por página
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      <Button
        variant="outline"
        size="sm"
        onClick={() => table.previousPage()}
        disabled={!table.getCanPreviousPage()}
      >
        Anterior
      </Button>
      {sortNote ? <span className="text-muted-foreground px-1 text-xs">{sortNote}</span> : null}
      {pageOf ? <span className="lex-num text-muted-foreground px-1 text-sm">{pageOf}</span> : null}
      <Button
        variant="outline"
        size="sm"
        onClick={() => table.nextPage()}
        disabled={!table.getCanNextPage()}
      >
        Próxima
      </Button>
    </nav>
  );
}
