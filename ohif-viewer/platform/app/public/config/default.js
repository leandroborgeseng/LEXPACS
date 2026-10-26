window.config = {
  routerBasename: '/viewer',
  showStudyList: true,
  extensions: [],
  modes: [],
  customizationService: {},
  showWarningMessageForCrossOrigin: true,
  showCPUFallbackMessage: true,
  showLoadingIndicator: true,
  strictZSpacingForMultiplanarReformat: true,
  maxNumberOfWebWorkers: 3,
  omitQuotationForMultipartRequest: true,
  investigationalUseDialog: {
    option: 'never',
  },
  dataSources: [
    {
      namespace: '@ohif/extension-default.dataSourcesModule.dicomweb',
      sourceName: 'dicomweb',
      configuration: {
        friendlyName: 'LEX PACS',
        name: 'lex-pacs',
        wadoUriRoot: '/wado',
        qidoRoot: '/dicom-web',
        wadoRoot: '/dicom-web',
        qidoSupportsIncludeField: false,
        imageRendering: 'wadors',
        thumbnailRendering: 'wadors',
        enableStudyLazyLoad: true,
        supportsFuzzyMatching: false,
        // LEX PACS: curinga no nome (mín. 3 letras, sem acento) — ver lexQidoFilters.js
        supportsWildcard: true,
        staticWado: false,
        singlepart: 'bulkdata,video,pdf',
        acceptHeader: [
          'multipart/related; type="application/octet-stream"; transfer-syntax=*',
        ],
        onConfiguration: (config) => {
          const hooks = [
            request => {
              request.withCredentials = true;
              return request;
            },
          ];
          return { ...config, requestHooks: hooks };
        },
      },
    },
  ],
  defaultDataSourceName: 'dicomweb',
  whiteLabeling: {
    createLogoComponentFn: function (React) {
      const base = (window.config && window.config.routerBasename) || '/viewer';
      const root = base.endsWith('/') ? base : `${base}/`;
      // LX11: LEX PACS no escuro; logo PMF (temporário, do SIGPMF) no claro, via CSS [data-theme='light'].
      return React.createElement(
        React.Fragment,
        null,
        React.createElement('img', {
          src: `${root}lex-pacs-logo.svg`,
          alt: 'LEX PACS',
          className: 'lex-logo-lex h-[28px] w-auto',
        }),
        React.createElement('img', {
          src: `${root}pmf-catavento.png`,
          alt: 'Prefeitura de Franca',
          hidden: true,
          className: 'lex-logo-pmf h-[28px] w-auto',
        })
      );
    },
  },
};
