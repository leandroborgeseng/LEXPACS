/**
 * LEX PACS — duplo clique na linha abre direto o visualizador básico (modo longitudinal,
 * rota /viewer), sem seletor de workflow nem segmentação. Se o usuário fixou um workflow
 * padrão, ele continua valendo.
 */
const BASIC_IDS = [/mode-longitudinal$/, /longitudinal/, /mode-basic$/];

export function lexDoubleClickWorkflow(applicable = []) {
  const list = Array.isArray(applicable) ? applicable : [];
  const def = list.find(w => w && w.isDefault);
  if (def) {
    return def;
  }
  for (const rx of BASIC_IDS) {
    const hit = list.find(w => w && rx.test(String(w.id ?? '')));
    if (hit) {
      return hit;
    }
  }
  return undefined;
}
