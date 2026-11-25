import React, { useCallback, useEffect, useState } from 'react';
import { useLocation, useParams } from 'react-router';
import { Enums, log } from '@ohif/core';
import { Button, lexSearchWholeArchive } from '@ohif/ui-next';
import { shallowEqualIgnoringArrayOrder } from '../utils/shallowEqualIgnoringArrayOrder';
import {
  URL_KEYS,
  getUrlParam,
  readLexTextFilters,
  LEX_TEXT_FILTERS_EVENT,
} from '../utils/studyListFilterContract';

export const LEX_INDEX_POLL_MS = 3000;

const DEFAULT_DATA = {
  studies: [],
  queryFilterValues: null,
  total: null as number | null,
  hasMore: false,
  sortScope: 'global' as string,
  partial: false,
  index: null as null | { status: string; indexed: number; total: number | null },
};

/**
 * Queries the data source for the study list and manages the result lifecycle:
 * refetch-on-filter-change, loading / first-fetch flags, and surfacing
 * connection errors (a modal with a Retry action). Pagination changes do not
 * trigger refetches — the study list paginates client-side.
 *
 * `refresh` invalidates the cached result and re-arms the first-fetch gate,
 * causing the next render to re-query. It also clears the loading flag, so the
 * caller can use it as the single reset when the active data source changes.
 */
export function useStudyListQuery({
  dataSource,
  isDataSourceInitialized,
  servicesManager,
}: {
  dataSource: any;
  isDataSourceInitialized: boolean;
  servicesManager: AppTypes.ServicesManager;
}): {
  studies: any[];
  /** LEX PACS: paginação no servidor (dataSource com lexWorklistApi). */
  serverPaging: boolean;
  total: number | null;
  hasMore: boolean;
  sortScope: string;
  /** Índice do portal ainda carregando: resultado parcial. */
  partial: boolean;
  index: null | { status: string; indexed: number; total: number | null };
  isLoading: boolean;
  hasFetchedOnce: boolean;
  refresh: () => void;
} {
  const location = useLocation();
  const params = useParams();

  const [data, setData] = useState(DEFAULT_DATA);
  const [isLoading, setIsLoading] = useState(false);
  const [hasFetchedOnce, setHasFetchedOnce] = useState(false);
  // LP9: filtros de texto vêm da sessionStorage; o evento força nova consulta.
  const [lexTextVersion, setLexTextVersion] = useState(0);
  useEffect(() => {
    const bump = () => setLexTextVersion(v => v + 1);
    window.addEventListener(LEX_TEXT_FILTERS_EVENT, bump);
    return () => window.removeEventListener(LEX_TEXT_FILTERS_EVENT, bump);
  }, []);

  const refresh = useCallback(() => {
    setIsLoading(false);
    setHasFetchedOnce(false);
    setData(DEFAULT_DATA);
  }, []);

  useEffect(() => {
    if (!isDataSourceInitialized) {
      return;
    }

    // Per-data-source result cap, passed to servers that honor the `limit`
    // query parameter. Defaults to 101 when the data source doesn't set it.
    const studiesLimit = dataSource.getConfig?.()?.queryLimit ?? 101;
    const serverPaging = Boolean(dataSource.getConfig?.()?.lexWorklistApi);
    const queryFilterValues = _getQueryFilterValues(location.search, studiesLimit, serverPaging);

    // 204: no content
    async function getData() {
      setIsLoading(true);
      log.time(Enums.TimingEnum.SEARCH_TO_LIST);
      try {
        const studies = await dataSource.query.studies.search(queryFilterValues);
        setData({
          studies: studies || [],
          queryFilterValues,
          total: Number.isFinite(studies?.lexTotal) ? studies.lexTotal : null,
          hasMore: Boolean(studies?.lexHasMore),
          sortScope: studies?.lexSortScope === 'page' ? 'page' : 'global',
          partial: Boolean(studies?.lexPartial),
          index: studies?.lexIndex ?? null,
        });
        log.timeEnd(Enums.TimingEnum.SCRIPT_TO_VIEW);
        log.timeEnd(Enums.TimingEnum.SEARCH_TO_LIST);
      } catch (e) {
        console.error(e);
        // Record that we attempted these filter values even though the fetch
        // failed. Without this, the effect's `filtersChanged` check would
        // remain true on the next render and immediately retry the same
        // failing query in a tight loop.
        setData(prev => ({ ...prev, queryFilterValues }));

        // If there is a data source configuration API, the Worklist will pop
        // up its own dialog to attempt to configure it. Otherwise surface the
        // failure via a modal with a Retry action.
        const { configurationAPI, friendlyName } = dataSource.getConfig();
        if (!configurationAPI) {
          const { uiModalService } = servicesManager.services;
          uiModalService.show({
            title: 'Data Source Connection Error',
            content: () => (
              <div className="text-foreground">
                <p className="text-red-600">Error: {(e as Error).message}</p>
                <p>
                  Please ensure the following data source is configured correctly or is running:
                </p>
                <div className="mt-2 font-bold">{friendlyName}</div>
                <div className="mt-4 flex justify-end">
                  <Button
                    onClick={() => {
                      uiModalService.hide();
                      refresh();
                    }}
                  >
                    Retry
                  </Button>
                </div>
              </div>
            ),
          });
        }
      } finally {
        setIsLoading(false);
        setHasFetchedOnce(true);
      }
    }

    // Refetch when the filter set has actually changed. Filters can include
    // array-valued fields like `modalitiesInStudy` whose element order
    // doesn't matter, so we compare with an unordered-array shallow equal
    // rather than reference equality — otherwise a re-render that
    // re-creates the array with the same contents would force a refetch.
    // Pagination changes alone don't invalidate the data (we paginate
    // client-side).
    const filtersChanged = !shallowEqualIgnoringArrayOrder(
      data.queryFilterValues,
      queryFilterValues
    );
    const isDataInvalid = !isLoading && filtersChanged;

    if (isDataInvalid) {
      getData();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, location, params, isLoading, dataSource, isDataSourceInitialized, lexTextVersion]);

  // Enquanto o índice prepara, consulta de novo a cada 3 s (sem limpar a lista atual).
  useEffect(() => {
    if (!data.partial || isLoading) {
      return;
    }
    const timer = window.setTimeout(
      () => setData(prev => ({ ...prev, queryFilterValues: null })),
      LEX_INDEX_POLL_MS
    );
    return () => window.clearTimeout(timer);
  }, [data, isLoading]);

  return {
    studies: data.studies,
    serverPaging: Boolean(dataSource?.getConfig?.()?.lexWorklistApi),
    total: data.total,
    hasMore: data.hasMore,
    sortScope: data.sortScope,
    partial: data.partial,
    index: data.index,
    isLoading,
    hasFetchedOnce,
    refresh,
  };
}

/**
 * Translates the URL query string into the filter shape expected by the
 * data source (`patientId`, `patientName`, `modalitiesInStudy`, …).
 *
 * URL keys come from the centralized contract in `studyListFilterContract.ts`,
 * which is also what WorkList's URL serializer writes — so the read/write
 * sides can't drift.
 *
 * @param {*} query - URL search string or `URLSearchParams`
 */
function _getQueryFilterValues(query, queryLimit, serverPaging = false) {
  const params = new URLSearchParams(query);
  // LP9: texto da sessionStorage tem precedência; a URL só vale para links antigos.
  const lexText = readLexTextFilters();
  Object.entries(lexText).forEach(([k, v]) => {
    if (v && !getUrlParam(params, k)) {
      params.set(k, v);
    }
  });
  // LEX PACS: com paginação no servidor, a página e o tamanho da URL viram offset/limit
  // (só a página atual é carregada, nunca os ~35 mil).
  const pageSize = Math.min(
    Math.max(parseInt(getUrlParam(params, URL_KEYS.resultsPerPage) ?? '', 10) || 50, 1),
    200
  );
  const pageIndex = Math.max((parseInt(getUrlParam(params, URL_KEYS.pageNumber) ?? '', 10) || 1) - 1, 0);
  const modalities = getUrlParam(params, URL_KEYS.modalities);

  const queryFilterValues = {
    // DCM
    patientId: getUrlParam(params, URL_KEYS.mrn),
    patientName: getUrlParam(params, URL_KEYS.patientName),
    studyDescription: getUrlParam(params, URL_KEYS.description),
    modalitiesInStudy: modalities ? modalities.split(',') : null,
    accessionNumber: getUrlParam(params, URL_KEYS.accession),
    //
    startDate: getUrlParam(params, URL_KEYS.startDate),
    endDate: getUrlParam(params, URL_KEYS.endDate),
    // Rarely supported server-side
    sortBy: getUrlParam(params, URL_KEYS.sortBy),
    sortDirection: getUrlParam(params, URL_KEYS.sortDirection),
    // So many different servers out there that we can't rely on them to support offset/limit.
    // So we just query for everything up to the queryLimit for those that support it.
    // For those that don't we will just assume we get everything back.
    offset: serverPaging ? pageIndex * pageSize : 0,
    limit: serverPaging ? pageSize : queryLimit,
  };

  // Delete null/undefined keys
  Object.keys(queryFilterValues).forEach(
    key => queryFilterValues[key] == null && delete queryFilterValues[key]
  );

  // LP19: com termo digitado (nome, prontuário, acesso, descrição), busca em todo o acervo,
  // ignorando o filtro de data (Hoje/Esta semana/Semana passada). Limpar volta ao filtro.
  return lexSearchWholeArchive(queryFilterValues);
}
