window.config = {
  routerBasename: '/viewer',
  showStudyList: true,
  extensions: [],
  modes: [],
  customizationService: {},
  showWarningMessageForCrossOrigin: true,
  showCPUFallbackMessage: false,
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
        supportsWildcard: false,
        staticWado: false,
        singlepart: 'bulkdata,video,pdf',
        acceptHeader: [
          'multipart/related; type="application/octet-stream"; transfer-syntax=*',
        ],
      },
    },
  ],
  defaultDataSourceName: 'dicomweb',
  whiteLabeling: {
    createLogoComponentFn: function (React) {
      return React.createElement('img', {
        src: './lex-pacs-logo.svg',
        alt: 'LEX PACS',
        className: 'h-[28px] w-auto',
      });
    },
  },
};
