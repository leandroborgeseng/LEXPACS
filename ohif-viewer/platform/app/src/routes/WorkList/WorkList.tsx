import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useAppConfig } from '@state';
import { preserveQueryParameters } from '../../utils/preserveQueryParameters';
import { useStudyListStateSync, useWorkListToolbarActions } from '../../hooks';

import {
  lexShowSearching,
  lexSortNote,
  lexIndexingMessage,
  LEX_INDEX_ERROR_MESSAGE,
  lexRetryLabel,
  LEX_SEARCHING_DELAY_MS,
  StudyList,
  Icons, InvestigationalUseDialog, LexThemeToggle, type StudyRow } from '@ohif/ui-next';
import { StudyListSettingsPopover } from './StudyListSettingsPopover';
import { SidePanelPreview } from './SidePanelPreview';
import { WorkListViewBar } from './WorkListViewBar';
import { filtersFromView, type WorklistView } from './WorkListViewBar';

type Props = withAppTypes & {
  data: any[];
  dataSource: any;
  isLoadingData: boolean;
  hasFetchedOnce?: boolean;
  dataPath?: string;
  /** LEX PACS: paginação no servidor (total null = desconhecido). */
  serverPaging?: boolean;
  dataTotal?: number | null;
  dataHasMore?: boolean;
  dataSortScope?: string;
  dataPartial?: boolean;
  dataIndex?: null | {
    status: string;
    indexed: number;
    total: number | null;
    retryInSeconds?: number;
  };
  onRefresh: () => void;
};

export default function WorkList({
  data,
  dataSource,
  isLoadingData,
  hasFetchedOnce = false,
  dataPath,
  serverPaging = false,
  dataTotal = null,
  dataHasMore = false,
  dataSortScope = 'global',
  dataPartial = false,
  dataIndex = null,
  onRefresh,
  servicesManager,
  extensionManager,
}: Props) {
  const { t, i18n } = useTranslation();
  const [appConfig] = useAppConfig();
  const { customizationService } = servicesManager.services;
  const LoadingIndicatorProgress = customizationService.getCustomization(
    'ui.loadingIndicatorProgress'
  ) as React.ComponentType<{ className?: string }> | undefined;
  const [isFilterPending, setIsFilterPending] = useState(false);
  const showStudyListLoading = Boolean(
    (appConfig.showLoadingIndicator && isLoadingData) || !hasFetchedOnce || isFilterPending
  );

  // Sync table state (sorting, pagination, filters) with URL and sessionStorage
  const { sorting, pagination, filters, activeView, setSorting, setPagination, setFilters, setActiveView } =
    useStudyListStateSync();

  // Default sorting if no URL state exists
  const defaultSorting = useMemo(() => [{ id: 'studyDateTime', desc: true }], []);

  const [selected, setSelected] = useState<StudyRow | null>(null);
  const [isPreviewOpen, setPreviewOpen] = useState(true);

  const columns = useMemo(() => {
    const customized = customizationService.getCustomization('workList.columns');
    if (Array.isArray(customized) && customized !== StudyList.defaultColumns) {
      return customized;
    }
    return StudyList.createDefaultColumns();
  }, [customizationService, i18n.language]);

  // VW2: no claro, logo PMF + "PACS PMF"; no escuro continua o LEX PACS (VW10).
  const publicRoot = `${(window as any).PUBLIC_URL ?? '/viewer/'}`.replace(/\/?$/, '/');
  const logoComponent = (
    <>
      <span className="lex-logo-lex">
        <Icons.LexPacsLogo
          aria-label="LEX PACS logo"
          className="h-[28px] w-auto shrink-0"
        />
      </span>
      <span
        className="lex-logo-pmf"
        hidden
      >
        <span className="flex items-center gap-2">
        <img
          src={`${publicRoot}pmf-catavento.png`}
          alt="Prefeitura de Franca"
          className="h-[28px] w-auto shrink-0"
        />
        <span className="lex-brand-name text-base">PACS PMF</span>
        </span>
      </span>
    </>
  );

  const toolbarActions = useWorkListToolbarActions(servicesManager, dataSource, onRefresh);

  const previewDefaultSize = useMemo(() => {
    if (typeof window !== 'undefined' && window.innerWidth > 0) {
      const percent = (325 / window.innerWidth) * 100;
      return Math.min(Math.max(percent, 15), 50);
    }
    return 30;
  }, []);

  // LEX PACS: "Buscando…" só se a busca passar de 1 s; filtros continuam visíveis.
  const [searchingSlow, setSearchingSlow] = useState(false);
  useEffect(() => {
    if (!isLoadingData) {
      setSearchingSlow(false);
      return;
    }
    const started = Date.now();
    const timer = window.setTimeout(
      () => setSearchingSlow(lexShowSearching(true, Date.now() - started)),
      LEX_SEARCHING_DELAY_MS
    );
    return () => window.clearTimeout(timer);
  }, [isLoadingData]);

  useEffect(() => {
    if (isLoadingData) {
      return;
    }
    setIsFilterPending(false);
  }, [isLoadingData, data]);

  useEffect(() => {
    if (!activeView || activeView === 'all') {
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch('/clinica-api/admin/pacs/worklist-views', {
          credentials: 'include',
        });
        const payload = await response.json().catch(() => ({}));
        if (cancelled || !response.ok || !Array.isArray(payload.views)) {
          return;
        }
        const preset = payload.views.find((v: WorklistView) => v.id === activeView);
        if (preset) {
          setFilters(filtersFromView(preset));
        }
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeView, setFilters]);

  const handleViewChange = (viewId: string, nextFilters: typeof filters) => {
    setActiveView(viewId);
    setIsFilterPending(true);
    setFilters(nextFilters);
  };

  return (
    <div className="bg-background flex h-screen min-h-0 flex-col overflow-hidden">
      <InvestigationalUseDialog dialogConfiguration={appConfig?.investigationalUseDialog} />
      <div className="flex h-full min-h-0 flex-col">
        <div className="flex min-h-0 flex-1 flex-col">
          <StudyList
            loadedModes={appConfig?.loadedModes ?? []}
            preserveQueryParameters={preserveQueryParameters}
            dataPath={dataPath}
            isPreviewOpen={isPreviewOpen}
            onIsPreviewOpenChange={setPreviewOpen}
            defaultPreviewSizePercent={previewDefaultSize}
            className="h-full w-full"
          >
            <StudyList.Table
              columns={columns}
              data={data as StudyRow[]}
              sorting={sorting.length > 0 ? sorting : defaultSorting}
              pagination={pagination}
              filters={filters}
              onSortingChange={setSorting}
              onPaginationChange={setPagination}
              manualPagination={serverPaging}
              manualFiltering={serverPaging}
              rowCount={serverPaging ? dataTotal : undefined}
              hasMore={dataHasMore}
              sortNote={serverPaging ? lexSortNote(dataSortScope) : null}
              emptyMessage={
                serverPaging && dataIndex?.status === 'error'
                  ? LEX_INDEX_ERROR_MESSAGE
                  : serverPaging && dataPartial
                    ? lexIndexingMessage(dataIndex)
                    : undefined
              }
              onFiltersChange={updater => {
                setIsFilterPending(true);
                setFilters(updater);
              }}
              isLoading={showStudyListLoading}
              loadingComponent={
                LoadingIndicatorProgress ? (
                  <LoadingIndicatorProgress className="!relative bg-background" />
                ) : (
                  <div className="h-8 w-8" />
                )
              }
              title={t('StudyList:StudyList')}
              onSelectionChange={sel => setSelected((sel as StudyRow[])[0] ?? null)}
              toolbarLeftComponent={logoComponent}
              toolbarRightActionsComponent={toolbarActions}
              toolbarBelowComponent={
                <>
                  <WorkListViewBar
                    activeView={activeView}
                    onViewChange={handleViewChange}
                  />
                  {serverPaging && dataIndex?.status === 'error' ? (
                    <div
                      role="alert"
                      className="text-muted-foreground px-3 py-1 text-sm"
                    >
                      {LEX_INDEX_ERROR_MESSAGE}
                      <LexIndexRetryButton
                        retryInSeconds={dataIndex?.retryInSeconds ?? 0}
                        onRetried={onRefresh}
                      />
                    </div>
                  ) : null}
                  {serverPaging && dataPartial ? (
                    <div
                      role="status"
                      aria-live="polite"
                      className="text-primary px-3 py-1 text-sm"
                    >
                      {lexIndexingMessage(dataIndex)}
                      <span className="text-muted-foreground ml-2">(resultados parciais)</span>
                    </div>
                  ) : null}
                  {searchingSlow ? (
                    <div
                      role="status"
                      aria-live="polite"
                      className="text-primary px-3 py-1 text-sm"
                    >
                      Buscando…
                    </div>
                  ) : null}
                </>
              }
              toolbarRightComponent={
                <div className="relative -top-px mt-1 ml-2 flex items-center gap-1">
                  <LexThemeToggle />
                  <StudyListSettingsPopover />
                  {!isPreviewOpen ? <StudyList.OpenPreviewButton /> : null}
                </div>
              }
            />
            <StudyList.Preview>
              <SidePanelPreview
                dataSource={dataSource}
                selected={selected}
                servicesManager={servicesManager}
              />
            </StudyList.Preview>
          </StudyList>
        </div>
      </div>
    </div>
  );
}


/**
 * "Tentar de novo" da carga do índice: desabilitado com contagem até passar o intervalo mínimo
 * (o backend aplica o mesmo intervalo e responde 429 antes disso).
 */
function LexIndexRetryButton({
  retryInSeconds,
  onRetried,
}: {
  retryInSeconds: number;
  onRetried: () => void;
}) {
  const [left, setLeft] = useState(Math.max(0, Math.ceil(retryInSeconds)));
  const [busy, setBusy] = useState(false);
  useEffect(() => setLeft(Math.max(0, Math.ceil(retryInSeconds))), [retryInSeconds]);
  useEffect(() => {
    if (left <= 0) {
      return;
    }
    const timer = window.setTimeout(() => setLeft(v => Math.max(0, v - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [left]);
  const retry = async () => {
    setBusy(true);
    try {
      const r = await fetch('/clinica-api/worklist/index/retry', {
        method: 'POST',
        credentials: 'include',
      });
      if (r.status === 429) {
        const body = await r.json().catch(() => ({}));
        setLeft(Number(body?.detail?.retryInSeconds) || Number(r.headers.get('Retry-After')) || 60);
        return;
      }
      onRetried();
    } finally {
      setBusy(false);
    }
  };
  return (
    <button
      type="button"
      className="border-input text-primary ml-3 rounded-md border px-2 py-0.5 text-sm disabled:opacity-60"
      disabled={busy || left > 0}
      aria-disabled={busy || left > 0}
      onClick={retry}
    >
      <span className="lex-num">{lexRetryLabel(left)}</span>
    </button>
  );
}
