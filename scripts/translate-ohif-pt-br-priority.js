#!/usr/bin/env node
/**
 * Traduz chaves pt-BR que ainda estão idênticas ao en-US (namespaces de uso frequente).
 * Uso: node scripts/translate-ohif-pt-br-priority.js
 */
const fs = require('fs');
const path = require('path');

const PT_DIR = path.join(__dirname, '../ohif-viewer/platform/i18n/src/locales/pt-BR');

/** namespace → { key: 'tradução pt-BR' } */
const OVERRIDES = {
  Buttons: {
    Axial: 'Axial',
    Cine: 'Cine',
    Coronal: 'Coronal',
    Manual: 'Manual',
    'Reference Lines': 'Linhas de referência',
    Reset: 'Restaurar',
    Zoom: 'Zoom',
    'Cobb Angle': 'Ângulo de Cobb',
    'Dicom Tag Browser': 'Navegador de tags DICOM',
    'Magnify Probe': 'Lupa de inspeção',
    'Ultrasound Directional': 'Ultrassom direcional',
    'Window Level Region': 'Região de janela/nível',
    'Change viewport orientation between axial, sagittal, coronal and reformat planes':
      'Alterar orientação do viewport (axial, sagital, coronal, reformatado)',
    Status: 'Status',
    'Rectangle ROI': 'ROI retangular',
    'Keep Aspect': 'Manter proporção',
    Point: 'Ponto',
    Polygon: 'Polígono',
    'Polygon Tool': 'Ferramenta polígono',
    Box: 'Caixa',
    'Box Tool': 'Ferramenta caixa',
    'Freehand Polygon': 'Polígono à mão livre',
    'Freehand Polygon Tool': 'Ferramenta polígono à mão livre',
    'Freehand Line': 'Linha à mão livre',
    'Freehand Line Tool': 'Ferramenta linha à mão livre',
    Line: 'Linha',
    'Line Tool': 'Ferramenta linha',
    '3D Rotate': 'Rotação 3D',
    Shape: 'Forma',
    MPR: 'MPR',
    'Rectangle ROI Threshold': 'Limiar ROI retangular',
    'Sculptor Tool': 'Ferramenta escultor',
    'Radius (mm)': 'Raio (mm)',
    'Catmull Rom Spline': 'Spline Catmull-Rom',
    'Linear Spline': 'Spline linear',
    'Simplified Spline': 'Spline simplificada',
    'Labelmap Assist': 'Assistente de labelmap',
    'US Pleura B-line Annotation': 'Anotação linha B pleural (US)',
  },
  Common: {
    Layout: 'Layout',
    mm: 'mm',
    Play: 'Reproduzir',
    RowsPerPage: 'linhas por página',
    Stop: 'Parar',
    StudyDate: 'Data do exame',
    localDateFormat: 'DD/MM/AAAA',
    Foreground: 'Primeiro plano',
    'SELECT A FOREGROUND': 'SELECIONE O PRIMEIRO PLANO',
    'SELECT A SEGMENTATION': 'SELECIONE A SEGMENTAÇÃO',
  },
  UserPreferencesModal: {
    Zoom: 'Zoom',
    Cine: 'Cine',
    'HotkeyKeys.ctrl': 'Ctrl',
    'HotkeyKeys.shift': 'Shift',
    'HotkeyKeys.alt': 'Alt',
    'HotkeyKeys.option': 'Option',
    'HotkeyKeys.meta': 'Cmd',
    'HotkeyKeys.enter': 'Enter',
    'HotkeyKeys.esc': 'Esc',
    'HotkeyKeys.tab': 'Tab',
    'HotkeyKeys.backspace': 'Backspace',
    'HotkeyKeys.insert': 'Insert',
    'HotkeyKeys.home': 'Home',
    'HotkeyKeys.end': 'End',
    'HotkeyKeys.pageup': 'Page Up',
    'HotkeyKeys.pagedown': 'Page Down',
    'HotkeyKeys.capslock': 'Caps Lock',
    'HotkeyKeys.comma': 'Vírgula',
    'HotkeyKeys.period': 'Ponto',
    'HotkeyKeys.slash': 'Barra',
    'HotkeyKeys.backslash': 'Barra invertida',
    'HotkeyKeys.semicolon': 'Ponto e vírgula',
    'HotkeyKeys.quote': 'Aspas',
    'HotkeyKeys.backquote': 'Acento grave',
    'HotkeyKeys.bracketleft': 'Colchete esquerdo',
    'HotkeyKeys.bracketright': 'Colchete direito',
  },
  MeasurementTable: {
    'No, do not ask again': 'Não, não perguntar novamente',
    NonTargets: 'Não alvos',
    Relabel: 'Renomear rótulo',
    Targets: 'Alvos',
    Rename: 'Renomear',
    Duplicate: 'Duplicar',
    'Change Color': 'Alterar cor',
    Lock: 'Bloquear',
    Unlock: 'Desbloquear',
    Hide: 'Ocultar',
    'Create SR': 'Criar SR',
    empty: 'vazio',
    'Track measurements for this series?': 'Rastrear medições desta série?',
    'Do you want to add this measurement to the existing report?':
      'Deseja adicionar esta medição ao laudo existente?',
    'You have existing tracked measurements. What would you like to do with your existing tracked measurements?':
      'Há medições rastreadas. O que deseja fazer com as medições existentes?',
    'Measurements cannot span across multiple studies. Do you want to save your tracked measurements?':
      'Medições não podem abranger vários exames. Deseja salvar as medições rastreadas?',
    'Do you want to continue tracking measurements for this study?':
      'Deseja continuar rastreando medições deste exame?',
    'Do you want to open this Segmentation?': 'Deseja abrir esta segmentação?',
    'There are unsaved measurements. Do you want to save it?':
      'Há medições não salvas. Deseja salvá-las?',
  },
  CineDialog: {
    fps: 'fps',
  },
  DatePicker: {
    Close: 'Fechar',
  },
  Messages: {
    14: '14',
    15: '15',
  },
  Onboarding: {
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
  },
  Hps: {
    MPR: 'MPR',
    '3D four up': '3D quatro painéis',
    'Frame View': 'Visualização por quadros',
    'Frame view for the active series': 'Visualização por quadros da série ativa',
    '3D main': '3D principal',
    mpr: 'MPR',
    '3D only': 'Somente 3D',
    '3D primary': '3D primário',
    'Axial Primary': 'Axial principal',
  },
  StudyBrowser: {
    Primary: 'Principal',
    Recent: 'Recentes',
    All: 'Todas',
    'Tracked Series': 'Séries rastreadas',
    'Add as Layer': 'Adicionar como camada',
    'Series Number': 'Número da série',
    'Series Date': 'Data da série',
    'Thumbnail Double Click': 'Duplo clique na miniatura',
    'The selected display sets could not be added to the viewport.':
      'Os conjuntos selecionados não puderam ser adicionados ao viewport.',
  },
  StudyList: {
    MRN: 'Prontuário',
  },
  DataSourceConfiguration: {
    'Configure Data Source': 'Configurar fonte de dados',
    'Data set': 'Conjunto de dados',
    'DICOM store': 'Armazenamento DICOM',
    Location: 'Localização',
    Project: 'Projeto',
    'Error fetching Data set list': 'Erro ao buscar conjuntos de dados',
    'Error fetching DICOM store list': 'Erro ao buscar armazenamentos DICOM',
    'Error fetching Location list': 'Erro ao buscar localizações',
    'Error fetching Project list': 'Erro ao buscar projetos',
    'No Project available': 'Nenhum projeto disponível',
    'No Location available': 'Nenhuma localização disponível',
    'No Data set available': 'Nenhum conjunto de dados disponível',
    'No DICOM store available': 'Nenhum armazenamento DICOM disponível',
    Select: 'Selecionar',
    'Search Data set list': 'Buscar conjuntos de dados',
    'Search DICOM store list': 'Buscar armazenamentos DICOM',
    'Search Location list': 'Buscar localizações',
    'Search Project list': 'Buscar projetos',
    'Select Data set': 'Selecione um conjunto de dados',
    'Select DICOM store': 'Selecione um armazenamento DICOM',
    'Select Location': 'Selecione uma localização',
    'Select Project': 'Selecione um projeto',
  },
};

let updated = 0;
for (const [ns, keys] of Object.entries(OVERRIDES)) {
  const file = path.join(PT_DIR, `${ns}.json`);
  if (!fs.existsSync(file)) {
    console.warn(`Namespace ausente: ${ns}.json`);
    continue;
  }
  const json = JSON.parse(fs.readFileSync(file, 'utf8'));
  let changed = 0;
  for (const [key, value] of Object.entries(keys)) {
    if (json[key] !== value) {
      json[key] = value;
      changed += 1;
      updated += 1;
    }
  }
  if (changed) {
    fs.writeFileSync(file, `${JSON.stringify(json, null, 2)}\n`);
    console.log(`${ns}: ${changed} chave(s) atualizada(s)`);
  }
}
console.log(`Total: ${updated} tradução(ões) aplicada(s) em pt-BR.`);
