import React, { useCallback, useEffect, useState } from 'react';
import { Button, Input, Tabs, TabsContent, TabsList, TabsTrigger } from '@ohif/ui-next';

const API_BASE = '/clinica-api/admin/pacs';
const AUTH_ME = '/clinica-api/auth/clinical/me';

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

type MwlEntry = {
  accession_number: string;
  patient_id: string;
  patient_name: string;
  modality: string;
  station_aet: string;
  procedure_description: string;
  scheduled_date: string;
};

type MwlStatus = {
  sql: {
    enabled: boolean;
    host: string;
    port: number;
    database: string;
    username: string;
    password_env?: string;
    table: string;
    sync_interval_minutes: number;
    password_configured: boolean;
  };
  sync: {
    last_at: string;
    last_synced: number;
    last_actor: string;
    last_error: string;
  };
  plugin_enabled: boolean;
  entries_total: number;
};

type MwlSqlForm = {
  enabled: boolean;
  host: string;
  port: number;
  database: string;
  username: string;
  password_env: string;
  table: string;
  sync_interval_minutes: number;
  password_configured: boolean;
};

type AuditEvent = {
  timestamp: string;
  event: string;
  actor: string;
};

type PacsStats = {
  patients: number;
  studies: number;
  series: number;
  instances: number;
  studies_by_modality: { modality: string; studies: number; series: number }[];
  study_date_age: { label: string; count: number }[];
  received_age: { label: string; count: number }[];
  disk: { label: string; bytes: number; mb: number }[];
  disk_total_mb: number;
  generated_at: string;
};

type PacsSettingsModalProps = {
  hide?: () => void;
};

const emptyMwlSql = (): MwlSqlForm => ({
  enabled: true,
  host: 'postgres',
  port: 5432,
  database: 'orthanc',
  username: 'orthanc',
  password_env: 'POSTGRES_PASSWORD',
  table: 'lex_mwl_schedule',
  sync_interval_minutes: 5,
  password_configured: false,
});

function mwlSqlFromStatus(sql: MwlStatus['sql']): MwlSqlForm {
  return {
    enabled: sql.enabled,
    host: sql.host,
    port: sql.port,
    database: sql.database,
    username: sql.username,
    password_env: sql.password_env || 'POSTGRES_PASSWORD',
    table: sql.table,
    sync_interval_minutes: sql.sync_interval_minutes,
    password_configured: sql.password_configured,
  };
}

const emptyEquipment = (): EquipmentItem => ({
  aet: '',
  host: '',
  port: 104,
  description: '',
  modality: '',
});

function formatTs(value: string): string {
  if (!value) {
    return '—';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString('pt-BR');
}

function formatCount(value: number): string {
  return value.toLocaleString('pt-BR');
}

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

  const [isAdmin, setIsAdmin] = useState(false);
  const [adminLoading, setAdminLoading] = useState(false);
  const [mwlStatus, setMwlStatus] = useState<MwlStatus | null>(null);
  const [mwlEntries, setMwlEntries] = useState<MwlEntry[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [mwlSql, setMwlSql] = useState<MwlSqlForm>(emptyMwlSql);
  const [pacsStats, setPacsStats] = useState<PacsStats | null>(null);

  const loadAdminData = useCallback(async () => {
    setAdminLoading(true);
    setError('');
    try {
      const [meRes, statusRes, entriesRes, statsRes] = await Promise.all([
        fetch(AUTH_ME, { credentials: 'include' }),
        fetch(`${API_BASE}/mwl/status`, { credentials: 'include' }),
        fetch(`${API_BASE}/mwl/entries`, { credentials: 'include' }),
        fetch(`${API_BASE}/stats`, { credentials: 'include' }),
      ]);
      const me = await meRes.json().catch(() => ({}));
      const status = await statusRes.json().catch(() => null);
      const entriesData = await entriesRes.json().catch(() => ({}));
      const statsData = await statsRes.json().catch(() => null);

      const groups: string[] = Array.isArray(me.groups) ? me.groups : [];
      const admin = groups.includes('admin') || me.username === 'admin';
      setIsAdmin(admin);

      if (!statusRes.ok) {
        throw new Error(status?.detail || 'Não foi possível carregar status MWL.');
      }
      setMwlStatus(status);
      setMwlSql(mwlSqlFromStatus(status.sql));
      setMwlEntries(Array.isArray(entriesData.entries) ? entriesData.entries.slice(0, 20) : []);
      if (statsRes.ok && statsData) {
        setPacsStats(statsData as PacsStats);
      } else {
        setPacsStats(null);
      }

      if (admin) {
        const auditRes = await fetch(`${API_BASE}/audit?limit=30`, { credentials: 'include' });
        const auditData = await auditRes.json().catch(() => ({}));
        if (auditRes.ok) {
          setAuditEvents(Array.isArray(auditData.events) ? auditData.events : []);
        } else {
          setAuditEvents([]);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar painel admin.');
    } finally {
      setAdminLoading(false);
    }
  }, []);

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

  useEffect(() => {
    if (tab === 'admin') {
      void loadAdminData();
    }
  }, [tab, loadAdminData]);

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

  const handleMwlSync = async () => {
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/mwl/sync`, {
        method: 'POST',
        credentials: 'include',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || 'Falha ao sincronizar MWL.');
      }
      setMessage(
        `MWL sincronizado: ${data.synced} arquivo(s), plugin ${data.plugin_enabled ? 'ativo' : 'inativo'}.`
      );
      await loadAdminData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao sincronizar MWL.');
    } finally {
      setSaving(false);
    }
  };

  const handleSaveMwlSql = async () => {
    if (!isAdmin) {
      return;
    }
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/mwl-sql`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          enabled: mwlSql.enabled,
          host: mwlSql.host.trim(),
          port: mwlSql.port,
          database: mwlSql.database.trim(),
          username: mwlSql.username.trim(),
          password_env: mwlSql.password_env.trim() || 'POSTGRES_PASSWORD',
          table: mwlSql.table.trim(),
          sync_interval_minutes: mwlSql.sync_interval_minutes,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || 'Não foi possível salvar configuração SQL.');
      }
      setMwlSql(mwlSqlFromStatus(data));
      setMessage('Configuração SQL MWL salva.');
      await loadAdminData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao salvar SQL MWL.');
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
    <div className="text-foreground flex w-[640px] flex-col gap-3 p-1">
      {loading ? (
        <p className="text-sm">Carregando…</p>
      ) : (
        <Tabs
          value={tab}
          onValueChange={setTab}
        >
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="server">Servidor</TabsTrigger>
            <TabsTrigger value="equipment">Equipamentos</TabsTrigger>
            <TabsTrigger value="worklist">Worklist</TabsTrigger>
            <TabsTrigger value="admin">Admin</TabsTrigger>
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

          <TabsContent
            value="admin"
            className="mt-4 flex max-h-[520px] flex-col gap-3 overflow-y-auto"
          >
            {adminLoading ? (
              <p className="text-sm">Carregando painel admin…</p>
            ) : mwlStatus ? (
              <>
                {pacsStats ? (
                  <div className="border-border rounded border p-3">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <p className="text-sm font-medium">Estatísticas do PACS</p>
                      <p className="text-muted-foreground text-xs">
                        Atualizado {formatTs(pacsStats.generated_at)}
                      </p>
                    </div>
                    <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                      {[
                        { label: 'Pacientes', value: pacsStats.patients },
                        { label: 'Exames', value: pacsStats.studies },
                        { label: 'Séries', value: pacsStats.series },
                        { label: 'Instâncias', value: pacsStats.instances },
                      ].map(item => (
                        <div
                          key={item.label}
                          className="bg-muted/40 rounded p-2 text-center"
                        >
                          <p className="text-lg font-semibold">{formatCount(item.value)}</p>
                          <p className="text-muted-foreground text-xs">{item.label}</p>
                        </div>
                      ))}
                    </div>

                    <div className="mb-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <div>
                        <p className="mb-1 text-xs font-medium">Exames por modalidade</p>
                        {pacsStats.studies_by_modality.length === 0 ? (
                          <p className="text-muted-foreground text-xs">Sem dados.</p>
                        ) : (
                          <table className="w-full text-left text-xs">
                            <thead>
                              <tr className="text-muted-foreground border-b">
                                <th className="py-1 pr-2">Mod.</th>
                                <th className="py-1 pr-2">Exames</th>
                                <th className="py-1">Séries</th>
                              </tr>
                            </thead>
                            <tbody>
                              {pacsStats.studies_by_modality.map(row => (
                                <tr
                                  key={row.modality}
                                  className="border-border/60 border-b"
                                >
                                  <td className="py-1 pr-2">{row.modality}</td>
                                  <td className="py-1 pr-2">{formatCount(row.studies)}</td>
                                  <td className="py-1">{formatCount(row.series)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </div>

                      <div>
                        <p className="mb-1 text-xs font-medium">Idade dos exames (data do estudo)</p>
                        <table className="w-full text-left text-xs">
                          <tbody>
                            {pacsStats.study_date_age.map(row => (
                              <tr
                                key={row.label}
                                className="border-border/60 border-b"
                              >
                                <td className="py-1 pr-2">{row.label}</td>
                                <td className="py-1 text-right">{formatCount(row.count)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    <div className="mb-3">
                      <p className="mb-1 text-xs font-medium">Idade na ingestão (última atualização)</p>
                      <table className="w-full text-left text-xs">
                        <tbody>
                          {pacsStats.received_age.map(row => (
                            <tr
                              key={`recv-${row.label}`}
                              className="border-border/60 border-b"
                            >
                              <td className="py-1 pr-2">{row.label}</td>
                              <td className="py-1 text-right">{formatCount(row.count)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    <div>
                      <p className="mb-1 text-xs font-medium">
                        Utilização de disco — total {pacsStats.disk_total_mb.toLocaleString('pt-BR')} MB
                      </p>
                      <table className="w-full text-left text-xs">
                        <tbody>
                          {pacsStats.disk.map(row => (
                            <tr
                              key={row.label}
                              className="border-border/60 border-b"
                            >
                              <td className="py-1 pr-2">{row.label}</td>
                              <td className="py-1 text-right">
                                {row.mb.toLocaleString('pt-BR')} MB
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : null}

                <div className="border-border rounded border p-3 text-sm">
                  <p className="font-medium">Status MWL</p>
                  <p className="text-muted-foreground mt-1 text-xs">
                    Plugin Orthanc: {mwlStatus.plugin_enabled ? 'ativo' : 'inativo'} · entradas SQL:{' '}
                    {mwlStatus.entries_total}
                  </p>
                  <p className="text-muted-foreground text-xs">
                    Último sync: {formatTs(mwlStatus.sync.last_at)} por{' '}
                    {mwlStatus.sync.last_actor || '—'} ({mwlStatus.sync.last_synced} arquivo(s))
                  </p>
                  {mwlStatus.sync.last_error ? (
                    <p className="text-destructive mt-1 text-xs">
                      Último erro: {mwlStatus.sync.last_error}
                    </p>
                  ) : null}
                  <div className="mt-2 flex gap-2">
                    <Button
                      size="sm"
                      onClick={handleMwlSync}
                      disabled={saving || !mwlSql.enabled}
                    >
                      Sincronizar MWL agora
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void loadAdminData()}
                      disabled={saving}
                    >
                      Atualizar
                    </Button>
                  </div>
                </div>

                <div className="border-border rounded border p-3">
                  <p className="mb-2 text-sm font-medium">Conexão SQL (agenda → MWL)</p>
                  {!isAdmin ? (
                    <p className="text-muted-foreground text-xs">
                      {mwlSql.host}:{mwlSql.port}/{mwlSql.database} · tabela {mwlSql.table} ·
                      sync a cada {mwlSql.sync_interval_minutes} min
                      {mwlSql.enabled ? '' : ' (desabilitado)'}
                    </p>
                  ) : (
                    <div className="flex flex-col gap-2">
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={mwlSql.enabled}
                          onChange={e => setMwlSql(prev => ({ ...prev, enabled: e.target.checked }))}
                        />
                        Sync SQL habilitado
                      </label>
                      <div className="grid grid-cols-2 gap-2">
                        <label className="flex flex-col gap-1 text-xs">
                          Host
                          <Input
                            value={mwlSql.host}
                            onChange={e => setMwlSql(prev => ({ ...prev, host: e.target.value }))}
                          />
                        </label>
                        <label className="flex flex-col gap-1 text-xs">
                          Porta
                          <Input
                            type="number"
                            value={mwlSql.port}
                            onChange={e =>
                              setMwlSql(prev => ({
                                ...prev,
                                port: Number(e.target.value) || 5432,
                              }))
                            }
                          />
                        </label>
                        <label className="flex flex-col gap-1 text-xs">
                          Banco
                          <Input
                            value={mwlSql.database}
                            onChange={e =>
                              setMwlSql(prev => ({ ...prev, database: e.target.value }))
                            }
                          />
                        </label>
                        <label className="flex flex-col gap-1 text-xs">
                          Usuário
                          <Input
                            value={mwlSql.username}
                            onChange={e =>
                              setMwlSql(prev => ({ ...prev, username: e.target.value }))
                            }
                          />
                        </label>
                        <label className="flex flex-col gap-1 text-xs">
                          Tabela
                          <Input
                            value={mwlSql.table}
                            onChange={e => setMwlSql(prev => ({ ...prev, table: e.target.value }))}
                          />
                        </label>
                        <label className="flex flex-col gap-1 text-xs">
                          Env da senha
                          <Input
                            value={mwlSql.password_env}
                            onChange={e =>
                              setMwlSql(prev => ({ ...prev, password_env: e.target.value }))
                            }
                            placeholder="POSTGRES_PASSWORD"
                          />
                        </label>
                        <label className="col-span-2 flex flex-col gap-1 text-xs">
                          Intervalo sync automático (minutos)
                          <Input
                            type="number"
                            min={1}
                            max={1440}
                            value={mwlSql.sync_interval_minutes}
                            onChange={e =>
                              setMwlSql(prev => ({
                                ...prev,
                                sync_interval_minutes: Math.max(
                                  1,
                                  Number(e.target.value) || 5
                                ),
                              }))
                            }
                          />
                        </label>
                      </div>
                      <p className="text-muted-foreground text-xs">
                        Senha via variável de ambiente{' '}
                        <span className="font-mono">{mwlSql.password_env}</span>:{' '}
                        {mwlSql.password_configured ? 'configurada' : 'ausente no servidor'}
                      </p>
                      <div className="flex justify-end">
                        <Button
                          size="sm"
                          onClick={handleSaveMwlSql}
                          disabled={saving}
                        >
                          Salvar conexão SQL
                        </Button>
                      </div>
                    </div>
                  )}
                </div>

                <div className="border-border rounded border p-3">
                  <p className="mb-2 text-sm font-medium">Prévia MWL (SQL)</p>
                  {mwlEntries.length === 0 ? (
                    <p className="text-muted-foreground text-xs">Nenhuma entrada agendada.</p>
                  ) : (
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="text-muted-foreground border-b">
                          <th className="py-1 pr-2">Accession</th>
                          <th className="py-1 pr-2">Paciente</th>
                          <th className="py-1 pr-2">Mod.</th>
                          <th className="py-1">Station</th>
                        </tr>
                      </thead>
                      <tbody>
                        {mwlEntries.map(entry => (
                          <tr
                            key={entry.accession_number}
                            className="border-border/60 border-b"
                          >
                            <td className="py-1 pr-2">{entry.accession_number}</td>
                            <td className="py-1 pr-2">{entry.patient_name}</td>
                            <td className="py-1 pr-2">{entry.modality}</td>
                            <td className="py-1">{entry.station_aet}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>

                {isAdmin ? (
                  <div className="border-border rounded border p-3">
                    <p className="mb-2 text-sm font-medium">Auditoria (últimos 30 eventos)</p>
                    {auditEvents.length === 0 ? (
                      <p className="text-muted-foreground text-xs">Nenhum evento registrado.</p>
                    ) : (
                      <table className="w-full text-left text-xs">
                        <thead>
                          <tr className="text-muted-foreground border-b">
                            <th className="py-1 pr-2">Quando</th>
                            <th className="py-1 pr-2">Evento</th>
                            <th className="py-1">Usuário</th>
                          </tr>
                        </thead>
                        <tbody>
                          {auditEvents.map((item, index) => (
                            <tr
                              key={`${item.timestamp}-${index}`}
                              className="border-border/60 border-b"
                            >
                              <td className="py-1 pr-2 whitespace-nowrap">
                                {formatTs(item.timestamp)}
                              </td>
                              <td className="py-1 pr-2">{item.event}</td>
                              <td className="py-1">{item.actor}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                ) : (
                  <p className="text-muted-foreground text-xs">
                    Log de auditoria visível apenas para usuários admin.
                  </p>
                )}
              </>
            ) : (
              <Button
                variant="outline"
                onClick={() => void loadAdminData()}
              >
                Carregar painel admin
              </Button>
            )}
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
