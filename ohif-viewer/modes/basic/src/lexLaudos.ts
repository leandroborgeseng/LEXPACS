/**
 * LD1/LD4: a aba "Laudos" (painel lexReport) só entra no layout quando o portal
 * confirma `laudos_visivel === true` (LEX_LAUDOS_HABILITADO=true E perfil com
 * can_draft/can_sign). Qualquer falha, ausência de sessão ou campo => sem aba.
 */
export const LEX_REPORT_PANEL_ID = '@ohif/extension-default.panelModule.lexReport';

export async function fetchLaudosVisivel(): Promise<boolean> {
  try {
    const response = await fetch('/clinica-api/auth/clinical/me', { credentials: 'include' });
    if (!response.ok) {
      return false;
    }
    const data = await response.json();
    return data?.laudos_visivel === true;
  } catch {
    return false;
  }
}

export function filterLexReportPanel(panels: string[] = [], visivel: boolean): string[] {
  return visivel ? panels : panels.filter(p => p !== LEX_REPORT_PANEL_ID);
}

export async function applyLaudosVisibility<T extends { props?: { rightPanels?: string[] } }>(
  layout: T
): Promise<T> {
  if (!layout?.props?.rightPanels?.includes(LEX_REPORT_PANEL_ID)) {
    return layout;
  }
  const visivel = await fetchLaudosVisivel();
  layout.props.rightPanels = filterLexReportPanel(layout.props.rightPanels, visivel);
  return layout;
}
