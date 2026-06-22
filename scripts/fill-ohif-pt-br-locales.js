#!/usr/bin/env node
/**
 * Preenche chaves ausentes em pt-BR a partir de en-US nos namespaces OHIF.
 * Mantém traduções existentes; aplica mapa PT para strings comuns.
 *
 * Uso: node scripts/fill-ohif-pt-br-locales.js
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const EN_DIR = path.join(ROOT, 'ohif-viewer/platform/i18n/src/locales/en-US');
const PT_DIR = path.join(ROOT, 'ohif-viewer/platform/i18n/src/locales/pt-BR');

/** Traduções por valor em inglês (en-US) → português (Brasil). */
const PT_BY_EN = {
  About: 'Sobre',
  Annotation: 'Anotação',
  'Accept Preview': 'Aceitar pré-visualização',
  'Add New Segment': 'Adicionar segmento',
  'Adjust window/level presets and customize image contrast settings':
    'Ajustar presets de janela/nível e contraste da imagem',
  'Advanced Window Level': 'Janela/nível avançado',
  'Advanced window/level settings with manual controls and presets':
    'Janela/nível avançado com controles manuais e presets',
  'Arrow Annotate': 'Anotação com seta',
  'Arrow Annotate Tool': 'Ferramenta de anotação com seta',
  Back: 'Voltar',
  'Back to {{location}}': 'Voltar para {{location}}',
  'Bidirectional Tool': 'Ferramenta bidirecional',
  Bone: 'Osso',
  Brain: 'Cérebro',
  Brush: 'Pincel',
  'B-Spline': 'B-spline',
  Calibration: 'Calibração',
  'Calibration Line': 'Linha de calibração',
  Cancel: 'Cancelar',
  'Cancel Measurement': 'Cancelar medição',
  Capture: 'Capturar',
  Cine: 'Cine',
  'Circle Tool': 'Ferramenta círculo',
  Clear: 'Limpar',
  'Clear Markers': 'Limpar marcadores',
  'Clear Filters': 'Limpar filtros',
  'Click to show or hide segment labels when hovering with your mouse.':
    'Clique para mostrar ou ocultar rótulos de segmento ao passar o mouse.',
  'Colorbar': 'Barra de cores',
  'Commit Hash': 'Hash do commit',
  'Configure data overlay options and manage foreground/background display sets':
    'Configurar sobreposição de dados e conjuntos em primeiro/segundo plano',
  'Create new segmentation to enable shapes tool.':
    'Crie uma segmentação para habilitar a ferramenta de formas.',
  'Create new segmentation to enable this tool.':
    'Crie uma segmentação para habilitar esta ferramenta.',
  'Criteria nonconformities': 'Não conformidades dos critérios',
  'Crosshairs': 'Localizador',
  'CrosshairsModifier': 'Localizador',
  'Current Browser & OS': 'Navegador e SO atuais',
  'Data Overlay': 'Sobreposição de dados',
  Delete: 'Excluir',
  'Delete Annotation': 'Excluir anotação',
  Description: 'Descrição',
  'Decrease Brush Size': 'Diminuir pincel',
  'Dismiss Aspect': 'Descartar proporção',
  Download: 'Baixar',
  Dynamic: 'Dinâmico',
  'Dynamic Cursor Size': 'Tamanho dinâmico do cursor',
  Eraser: 'Borracha',
  Exclude: 'Excluir',
  'Ellipse ROI': 'ROI elíptica',
  'Ellipse Tool': 'Ferramenta elipse',
  'Enable position synchronization on stack viewports':
    'Sincronizar posição em viewports de stack',
  'Filter list to 100 studies or less to enable sorting':
    'Filtre a lista para 100 exames ou menos para habilitar ordenação',
  'First Image': 'Primeira imagem',
  'Flip Horizontally': 'Inverter horizontalmente',
  'Flip Horizontal': 'Inverter horizontalmente',
  'Flip Vertically': 'Inverter verticalmente',
  'Flip H': 'Inverter H',
  'Flip V': 'Inverter V',
  'Freehand ROI': 'ROI à mão livre',
  'Freehand Segmentation': 'Segmentação à mão livre',
  'Grid Layout': 'Layout em grade',
  Hotkeys: 'Atalhos',
  'HotkeyKeys.ctrl': 'Ctrl',
  'HotkeyKeys.shift': 'Shift',
  'HotkeyKeys.alt': 'Alt',
  'HotkeyKeys.meta': 'Cmd',
  'HotkeyKeys.enter': 'Enter',
  'HotkeyKeys.esc': 'Esc',
  'HotkeyKeys.space': 'Espaço',
  'HotkeyKeys.tab': 'Tab',
  'HotkeyKeys.backspace': 'Backspace',
  'HotkeyKeys.delete': 'Delete',
  'HotkeyKeys.insert': 'Insert',
  'HotkeyKeys.home': 'Home',
  'HotkeyKeys.end': 'End',
  'HotkeyKeys.pageup': 'Page Up',
  'HotkeyKeys.pagedown': 'Page Down',
  'HotkeyKeys.up': 'Seta para cima',
  'HotkeyKeys.down': 'Seta para baixo',
  'HotkeyKeys.left': 'Seta para esquerda',
  'HotkeyKeys.right': 'Seta para direita',
  'HotkeyKeys.capslock': 'Caps Lock',
  'HotkeyKeys.plus': 'Mais',
  'HotkeyKeys.minus': 'Menos',
  'Increase Brush Size': 'Aumentar pincel',
  Include: 'Incluir',
  'Interpolate Contours': 'Interpolar contornos',
  'Interpolate Labelmap': 'Interpolar labelmap',
  'Interpolate Scroll': 'Rolagem interpolada',
  Invert: 'Inverter',
  'Invert Colors': 'Inverter cores',
  'Image Overlay': 'Sobreposição de imagem',
  'Image opacity settings': 'Configurações de opacidade da imagem',
  'Image Slice Sync': 'Sincronização de fatias',
  'Image threshold settings': 'Configurações de limiar da imagem',
  Language: 'Idioma',
  'LanguageName.en-US': 'Inglês (EUA)',
  'LanguageName.pt-BR': 'Português (Brasil)',
  'LanguageName.es': 'Espanhol',
  'Last Image': 'Última imagem',
  'Last 7 days': 'Últimos 7 dias',
  'Last 30 days': 'Últimos 30 dias',
  'Length Tool': 'Ferramenta de comprimento',
  'Livewire Contour': 'Contorno livewire',
  'Livewire tool': 'Ferramenta livewire',
  LOAD: 'CARREGAR',
  Liver: 'Fígado',
  Logout: 'Sair',
  Lung: 'Pulmão',
  'Marker Guided Labelmap': 'Labelmap guiado por marcador',
  'Marker Mode': 'Modo marcador',
  MAX: 'MÁX',
  Measurements: 'Medidas',
  'Modifier Keys': 'Teclas modificadoras',
  'More Measure Tools': 'Mais ferramentas de medição',
  'More Tools': 'Mais ferramentas',
  'Navigate between segments/measurements and manage their visibility':
    'Navegar entre segmentos/medições e gerenciar visibilidade',
  Navigation: 'Navegação',
  'Next Image': 'Próxima imagem',
  'Next Image Viewport': 'Próximo viewport de imagem',
  'Next Series': 'Próxima série',
  'Next Stage': 'Próximo estágio',
  'No hotkeys found':
    'Nenhum atalho configurado. Atalhos podem ser definidos no app-config.js.',
  'No segmentations available': 'Nenhuma segmentação disponível',
  'No Study Date': 'Sem data do exame',
  'Not available on the current viewport': 'Indisponível no viewport atual',
  'One Click Segment': 'Segmentar com um clique',
  Opacity: 'Opacidade',
  Orientation: 'Orientação',
  'PlusLeftClick': 'Clique esquerdo +',
  Pan: 'Arrastar',
  'Point Tool': 'Ferramenta ponto',
  'Press keys': 'Pressione as teclas…',
  'Press keys...': 'Pressione as teclas…',
  'Previous Image': 'Imagem anterior',
  'Previous Image Viewport': 'Viewport de imagem anterior',
  'Previous Series': 'Série anterior',
  'Previous Stage': 'Estágio anterior',
  'Previous Month': 'Mês anterior',
  'Next Month': 'Próximo mês',
  'Reject Preview': 'Rejeitar pré-visualização',
  Range: 'Intervalo',
  Redo: 'Refazer',
  Reset: 'Restaurar',
  'Reset to defaults': 'Restaurar padrões',
  'Reset to Defaults': 'Restaurar padrões',
  'Reset View': 'Restaurar visualização',
  'Rotate Right': 'Girar à direita',
  'Rotate Left': 'Girar à esquerda',
  'Rotate +90': 'Girar +90°',
  'RowsPerPage': 'linhas por página',
  Save: 'Salvar',
  'SaveMessage': 'Preferências salvas',
  'Select language': 'Selecionar idioma',
  'Select Month': 'Selecionar mês',
  'Select Year': 'Selecionar ano',
  Series: 'Séries',
  'Segment Bidirectional': 'Segmento bidirecional',
  'Segment Label Display': 'Exibir rótulo do segmento',
  'Select a 3D viewport to enable this tool': 'Selecione um viewport 3D para habilitar esta ferramenta',
  'Select an MPR viewport to enable this tool': 'Selecione um viewport MPR para habilitar esta ferramenta',
  'Select the PT Axial to enable this tool': 'Selecione PT Axial para habilitar esta ferramenta',
  Shapes: 'Formas',
  Show: 'Mostrar',
  'Show Reference Lines': 'Mostrar linhas de referência',
  'Soft tissue': 'Partes moles',
  Sphere: 'Esfera',
  'Spline ROI': 'ROI spline',
  'Spline Contour Segmentation Tool': 'Segmentação por contorno spline',
  'Spline Type': 'Tipo de spline',
  'Stack Image Sync': 'Sincronizar imagens do stack',
  Status: 'Status',
  Stop: 'Parar',
  'Threshold Tool': 'Ferramenta de limiar',
  'Threshold Tools': 'Ferramentas de limiar',
  Threshold: 'Limiar',
  Today: 'Hoje',
  'Toggle Image Overlay': 'Alternar sobreposição de imagem',
  'Tool not available for this modality': 'Ferramenta indisponível para esta modalidade',
  'Tracking Status': 'Status de rastreamento',
  Undo: 'Desfazer',
  'User preferences': 'Preferências do usuário',
  'View and manage tracking status of measurements and annotations':
    'Ver e gerenciar rastreamento de medições e anotações',
  'W/L Preset 1': 'Preset J/N 1',
  'W/L Preset 2': 'Preset J/N 2',
  'W/L Preset 3': 'Preset J/N 3',
  'W/L Preset 4': 'Preset J/N 4',
  'W/L Presets': 'Presets J/N',
  'Window Level': 'Janela/nível',
  Yes: 'Sim',
  No: 'Não',
  Zoom: 'Zoom',
  'Zoom In': 'Aumentar zoom',
  'Zoom Out': 'Diminuir zoom',
  'Zoom to Fit': 'Ajustar à tela',
  'Zoom-in': 'Aumentar zoom',
  mm: 'mm',
  'Display Set Messages': 'Mensagens do conjunto de exibição',
  'Dicom Tag Browser': 'Navegador de tags DICOM',
  'Tag Browser': 'Navegador de tags',
  'Compare two studies in various layouts': 'Comparar dois exames em vários layouts',
  'Compare Two Studies': 'Comparar dois exames',
  'Mammography Breast Screening': 'Mamografia — rastreamento',
  'Scrolling Through Images': 'Navegar pelas imagens',
  'You can scroll through the images using the mouse wheel or scrollbar.':
    'Role as imagens com a roda do mouse ou a barra de rolagem.',
  'Zooming In and Out': 'Aumentar e diminuir zoom',
  'You can zoom the images using the right click.':
    'Amplie as imagens com o clique direito.',
  'Panning the Image': 'Arrastar a imagem',
  'You can pan the images using the middle click.':
    'Arraste as imagens com o clique do meio.',
  'Adjusting Window Level': 'Ajustar janela/nível',
  'You can modify the window level using the left click.':
    'Modifique a janela/nível com o clique esquerdo.',
  'Using the Measurement Tools': 'Usar ferramentas de medição',
  'You can measure the length of a region using the Length tool.':
    'Meça o comprimento de uma região com a ferramenta Comprimento.',
  'Drawing Length Annotations': 'Desenhar medições de comprimento',
  'Use the length tool on the viewport to measure the length of a region.':
    'Use a ferramenta de comprimento no viewport para medir uma região.',
  'Tracking Measurements in the Panel': 'Rastrear medições no painel',
  'Click yes to track the measurements in the measurement panel.':
    'Clique em sim para rastrear as medições no painel.',
  'Opening the Measurements Panel': 'Abrir painel de medições',
  'Click the measurements button to open the measurements panel.':
    'Clique no botão de medições para abrir o painel.',
  'Scrolling Away from a Measurement': 'Rolar para longe de uma medição',
  'Scroll the images using the mouse wheel away from the measurement.':
    'Role as imagens com a roda do mouse para sair da medição.',
  'Jumping to Measurements in the Panel': 'Ir para medições no painel',
  'Click the measurement in the measurement panel to jump to it.':
    'Clique na medição no painel para ir até ela.',
  'Changing Layout': 'Alterar layout',
  'You can change the layout of the viewer using the layout button.':
    'Altere o layout do visualizador pelo botão de layout.',
  'Selecting the MPR Layout': 'Selecionar layout MPR',
  'Select the MPR layout to view the images in MPR mode.':
    'Selecione o layout MPR para ver as imagens em modo MPR.',
  'Skip all': 'Pular tudo',
};

function translateValue(enValue) {
  if (typeof enValue !== 'string') {
    return enValue;
  }
  if (enValue.startsWith('$t(')) {
    return enValue;
  }
  if (PT_BY_EN[enValue]) {
    return PT_BY_EN[enValue];
  }
  return enValue;
}

function mergeLocale(enObj, ptObj = {}) {
  const out = { ...ptObj };
  for (const [key, enValue] of Object.entries(enObj)) {
    if (out[key] === undefined) {
      out[key] = translateValue(enValue);
    }
  }
  return out;
}

function main() {
  const enFiles = fs.readdirSync(EN_DIR).filter(f => f.endsWith('.json'));
  let added = 0;
  let created = 0;

  for (const file of enFiles) {
    const en = JSON.parse(fs.readFileSync(path.join(EN_DIR, file), 'utf8'));
    const ptPath = path.join(PT_DIR, file);
    const hadFile = fs.existsSync(ptPath);
    const pt = hadFile ? JSON.parse(fs.readFileSync(ptPath, 'utf8')) : {};
    const before = Object.keys(pt).length;
    const merged = mergeLocale(en, pt);
    const after = Object.keys(merged).length;
    added += after - before;
    if (!hadFile) {
      created += 1;
    }
    fs.writeFileSync(ptPath, `${JSON.stringify(merged, null, 2)}\n`);
  }

  console.log(`pt-BR: ${created} namespace(s) criado(s), ${added} chave(s) adicionada(s).`);
}

main();
