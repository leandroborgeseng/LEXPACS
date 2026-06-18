import React, { useEffect, useState } from 'react';
import { Button, Input, Tabs, TabsContent, TabsList, TabsTrigger } from '@ohif/ui-next';

const API_BASE = '/clinica-api/admin/pacs';

type EquipmentItem = {
  id?: string;
  aet: string;
  host: string;
  port: number;
  description: string;
  modality: string;
};

type WorklistViewItem = {
  id: string;
  label: string;
  modalities: string[];
  description: string;
  station_aet: string;
};

type PacsSettingsModalProps = {
  hide?: () => void;
};

const emptyEquipment = (): EquipmentItem => ({
  aet: '',
  host: '',
  port: 104,
  description: '',
  modality: '',
});

export function PacsSettingsModal({ hide }: PacsSettingsModalProps) {
  const [tab, setTab] = useState('server');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const [dicomAet, setDicomAet] = useState('');
  const [dicomPort, setDicomPort] = useState('');
  const [institutionName, setInstitutionName] = useState('');
  const [checkCalledAet, setCheckCalledAet] = useState(false);

  const [equipment, setEquipment] = useState<EquipmentItem[]>([]);
  const [views, setViews] = useState<WorklistViewItem[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [settingsRes, equipmentRes, viewsRes] = await Promise.all([
          fetch(`${API_BASE}/settings`, { credentials: 'include' }),
          fetch(`${API_BASE}/equipment`, { credentials: 'include' }),
          fetch(`${API_BASE}/worklist-views`, { credentials: 'include' }),
        ]);
        const settings = await settingsRes.json().catch(() => ({}));
        const equipmentData = await equipmentRes.json().catch(() => ({}));
        const viewsData = await viewsRes.json().catch(() => ({}));
        if (!settingsRes.ok) {
          throw new Error(settings.detail || 'Não foi possível carregar as configurações.');
        }
        if (!cancelled) {
          setDicomAet(settings.dicom_aet || '');
          setDicomPort(String(settings.dicom_port || ''));
          setInstitutionName(settings.name || '');
          setCheckCalledAet(Boolean(settings.dicom_check_called_aet));
          setEquipment(Array.isArray(equipmentData.items) ? equipmentData.items : []);
          setViews(Array.isArray(viewsData.views) ? viewsData.views : []);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Erro ao carregar configurações.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSaveServer = async () => {
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/settings`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dicom_aet: dicomAet.trim().toUpperCase(),
          name: institutionName.trim(),
          dicom_check_called_aet: checkCalledAet,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || 'Não foi possível salvar.');
      }
      setMessage(data.message || 'Configurações do servidor salvas.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao salvar.');
    } finally {
      setSaving(false);
    }
  };

  const handleSaveEquipment = async () => {
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/equipment`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: equipment }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || 'Não foi possível salvar equipamentos.');
      }
      setEquipment(data.items || equipment);
      setMessage('Equipamentos salvos e sincronizados com o servidor DICOM.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao salvar.');
    } finally {
      setSaving(false);
    }
  };

  const handleSaveViews = async () => {
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/worklist-views`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ views }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || 'Não foi possível salvar visões.');
      }
      setViews(data.views || views);
      setMessage('Visões de worklist salvas.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao salvar.');
    } finally {
      setSaving(false);
    }
  };

  const updateEquipment = (index: number, patch: Partial<EquipmentItem>) => {
    setEquipment(prev => prev.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  };

  const updateView = (index: number, patch: Partial<WorklistViewItem>) => {
    setViews(prev => prev.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  };

  return (
    <div className="text-foreground flex w-[520px] flex-col gap-3 p-1">
      {loading ? (
        <p className="text-sm">Carregando…</p>
      ) : (
        <Tabs
          value={tab}
          onValueChange={setTab}
        >
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="server">Servidor</TabsTrigger>
            <TabsTrigger value="equipment">Equipamentos</TabsTrigger>
            <TabsTrigger value="worklist">Worklist</TabsTrigger>
          </TabsList>

          <TabsContent
            value="server"
            className="mt-4 flex flex-col gap-3"
          >
            <label className="flex flex-col gap-1 text-sm">
              Nome da instituição
              <Input
                value={institutionName}
                onChange={e => setInstitutionName(e.target.value)}
                maxLength={64}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              AE Title
              <Input
                value={dicomAet}
                onChange={e => setDicomAet(e.target.value.toUpperCase())}
                maxLength={16}
              />
            </label>
            <label className="text-muted-foreground flex flex-col gap-1 text-sm">
              Porta DICOM
              <Input
                value={dicomPort}
                readOnly
                disabled
              />
            </label>
            <p className="text-muted-foreground text-xs">
              A porta DICOM é definida no servidor. Alterá-la exige ajuste de firewall e reinício
              manual do container.
            </p>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={checkCalledAet}
                onChange={e => setCheckCalledAet(e.target.checked)}
              />
              Verificar AE Title chamado nas conexões recebidas
            </label>
            <div className="flex justify-end">
              <Button
                onClick={handleSaveServer}
                disabled={saving}
              >
                Salvar servidor
              </Button>
            </div>
          </TabsContent>

          <TabsContent
            value="equipment"
            className="mt-4 flex max-h-[360px] flex-col gap-3 overflow-y-auto"
          >
            {equipment.map((item, index) => (
              <div
                key={item.id || index}
                className="border-border flex flex-col gap-2 rounded border p-3"
              >
                <div className="grid grid-cols-2 gap-2">
                  <Input
                    placeholder="AE Title"
                    value={item.aet}
                    onChange={e => updateEquipment(index, { aet: e.target.value.toUpperCase() })}
                  />
                  <Input
                    placeholder="Modalidade (DX, CT…)"
                    value={item.modality}
                    onChange={e => updateEquipment(index, { modality: e.target.value.toUpperCase() })}
                  />
                  <Input
                    placeholder="IP / host"
                    value={item.host}
                    onChange={e => updateEquipment(index, { host: e.target.value })}
                  />
                  <Input
                    placeholder="Porta"
                    type="number"
                    value={item.port}
                    onChange={e => updateEquipment(index, { port: Number(e.target.value) || 104 })}
                  />
                </div>
                <Input
                  placeholder="Descrição (ex.: RX Sala 1)"
                  value={item.description}
                  onChange={e => updateEquipment(index, { description: e.target.value })}
                />
                <Button
                  variant="ghost"
                  size="sm"
                  className="self-end"
                  onClick={() => setEquipment(prev => prev.filter((_, i) => i !== index))}
                >
                  Remover
                </Button>
              </div>
            ))}
            <Button
              variant="outline"
              onClick={() => setEquipment(prev => [...prev, emptyEquipment()])}
            >
              Adicionar equipamento
            </Button>
            <div className="flex justify-end">
              <Button
                onClick={handleSaveEquipment}
                disabled={saving}
              >
                Salvar equipamentos
              </Button>
            </div>
          </TabsContent>

          <TabsContent
            value="worklist"
            className="mt-4 flex max-h-[360px] flex-col gap-3 overflow-y-auto"
          >
            <p className="text-muted-foreground text-xs">
              Visões salvas aparecem na barra da worklist. Use o id na URL: ?view=rx-sala-1
            </p>
            {views.map((view, index) => (
              <div
                key={view.id}
                className="border-border flex flex-col gap-2 rounded border p-3"
              >
                <div className="grid grid-cols-2 gap-2">
                  <Input
                    placeholder="id (rx-sala-1)"
                    value={view.id}
                    onChange={e => updateView(index, { id: e.target.value })}
                  />
                  <Input
                    placeholder="Nome exibido"
                    value={view.label}
                    onChange={e => updateView(index, { label: e.target.value })}
                  />
                </div>
                <Input
                  placeholder="Modalidades (CT,MR)"
                  value={(view.modalities || []).join(',')}
                  onChange={e =>
                    updateView(index, {
                      modalities: e.target.value
                        .split(',')
                        .map(v => v.trim().toUpperCase())
                        .filter(Boolean),
                    })
                  }
                />
                <Input
                  placeholder="Filtro descrição"
                  value={view.description}
                  onChange={e => updateView(index, { description: e.target.value })}
                />
                <Input
                  placeholder="Station AE (futuro MWL)"
                  value={view.station_aet}
                  onChange={e => updateView(index, { station_aet: e.target.value.toUpperCase() })}
                />
              </div>
            ))}
            <div className="flex justify-end">
              <Button
                onClick={handleSaveViews}
                disabled={saving}
              >
                Salvar visões
              </Button>
            </div>
          </TabsContent>
        </Tabs>
      )}

      {error ? <p className="text-destructive text-sm">{error}</p> : null}
      {message ? <p className="text-primary text-sm">{message}</p> : null}

      <div className="flex justify-end pt-1">
        <Button
          variant="ghost"
          onClick={hide}
          disabled={saving}
        >
          Fechar
        </Button>
      </div>
    </div>
  );
}

export default PacsSettingsModal;
