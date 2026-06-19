import React, { useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { Button, Input, Tabs, TabsContent, TabsList, TabsTrigger } from '@ohif/ui-next';
import { PacsStatsPanel } from './PacsStatsCharts';

const API_BASE = '/clinica-api/admin/pacs';
const AUTH_ME = '/clinica-api/auth/clinical/me';

/** Shell do Dialog OHIF — tamanho fixo com scroll interno. */
export const PACS_MODAL_SHELL =
  '!flex !max-w-[min(920px,calc(100vw-2rem))] !w-[min(920px,calc(100vw-2rem))] !max-h-[min(90vh,900px)] flex-col overflow-hidden';

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

type BackupStatus = {
  configured: boolean;
  success: boolean;
  last_at: string;
  last_path: string;
  lex_pacs_version: string;
  backup_root: string;
  retention_days: number;
  retention_daily: number;
  retention_weekly: number;
  interval_hours: number;
  error?: string;
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

function formatTs(value: string, locale: string): string {
  if (!value) {
    return '—';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString(locale);
}

export function PacsSettingsModal({ hide }: PacsSettingsModalProps) {
  const { t, i18n } = useTranslation('LexPacs');
  const [tab, setTab] = useState('server');
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [statsLoading, setStatsLoading] = useState(false);
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
  const [backupStatus, setBackupStatus] = useState<BackupStatus | null>(null);

  const loadStats = useCallback(async () => {
    setStatsLoading(true);
    try {
      const [statsRes, backupRes] = await Promise.all([
        fetch(`${API_BASE}/stats`, { credentials: 'include' }),
        fetch(`${API_BASE}/backup/status`, { credentials: 'include' }),
      ]);
      const statsData = await statsRes.json().catch(() => null);
      const backupData = await backupRes.json().catch(() => null);
      if (statsRes.ok && statsData) {
        setPacsStats(statsData as PacsStats);
      }
      if (backupRes.ok && backupData) {
        setBackupStatus(backupData as BackupStatus);
      }
    } catch {
      setPacsStats(null);
    } finally {
      setStatsLoading(false);
    }
  }, []);

  const loadAdminData = useCallback(async () => {
    setAdminLoading(true);
    setError('');
    try {
      const [meRes, statusRes, entriesRes] = await Promise.all([
        fetch(AUTH_ME, { credentials: 'include' }),
        fetch(`${API_BASE}/mwl/status`, { credentials: 'include' }),
        fetch(`${API_BASE}/mwl/entries`, { credentials: 'include' }),
      ]);
      const me = await meRes.json().catch(() => ({}));
      const status = await statusRes.json().catch(() => null);
      const entriesData = await entriesRes.json().catch(() => ({}));

      const permissions = me.permissions as { can_admin?: boolean } | undefined;
      const admin = Boolean(permissions?.can_admin);
      setIsAdmin(admin);

      if (!statusRes.ok) {
        throw new Error(status?.detail || t('pacsSettings.errors.loadMwl'));
      }
      setMwlStatus(status);
      setMwlSql(mwlSqlFromStatus(status.sql));
      setMwlEntries(Array.isArray(entriesData.entries) ? entriesData.entries.slice(0, 20) : []);
      await loadStats();

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
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.loadAdmin'));
    } finally {
      setAdminLoading(false);
    }
  }, [loadStats]);

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
          throw new Error(settings.detail || t('pacsSettings.errors.loadSettings'));
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
          setError(err instanceof Error ? err.message : t('pacsSettings.errors.loadSettings'));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    void loadStats();
    return () => {
      cancelled = true;
    };
  }, [loadStats]);

  useEffect(() => {
    if (tab === 'admin') {
      void loadAdminData();
    }
  }, [tab, loadAdminData]);

  useEffect(() => {
    if (!expanded) {
      return;
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setExpanded(false);
      }
    };
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = '';
      window.removeEventListener('keydown', onKey);
    };
  }, [expanded]);

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
        throw new Error(data.detail || t('pacsSettings.errors.save'));
      }
      setMessage(data.message || t('pacsSettings.messages.serverSaved'));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.save'));
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
        throw new Error(data.detail || t('pacsSettings.errors.saveEquipment'));
      }
      setEquipment(data.items || equipment);
      setMessage(t('pacsSettings.messages.equipmentSaved'));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.saveEquipment'));
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
        throw new Error(data.detail || t('pacsSettings.errors.saveViews'));
      }
      setViews(data.views || views);
      setMessage(t('pacsSettings.messages.viewsSaved'));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.saveViews'));
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
        throw new Error(data.detail || t('pacsSettings.errors.mwlSync'));
      }
      setMessage(
        t('pacsSettings.messages.mwlSynced', {
          count: data.synced,
          status: data.plugin_enabled ? t('pacsSettings.mwlActive') : t('pacsSettings.mwlInactive'),
        })
      );
      await loadAdminData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.mwlSync'));
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
        throw new Error(data.detail || t('pacsSettings.errors.saveSql'));
      }
      setMwlSql(mwlSqlFromStatus(data));
      setMessage(t('pacsSettings.messages.sqlSaved'));
      await loadAdminData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.saveSql'));
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

  const refreshData = () => {
    void (tab === 'admin' ? loadAdminData() : loadStats());
  };

  const panelBody = (
    <>
      <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={refreshData}
          disabled={saving || statsLoading || adminLoading}
        >
          {statsLoading || adminLoading ? t('pacsSettings.refreshing') : t('pacsSettings.refresh')}
        </Button>
        {!expanded ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setExpanded(true)}
          >
            {t('pacsSettings.fullscreen')}
          </Button>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto overscroll-contain pr-1">
        {loading ? (
          <p className="text-sm">{t('pacsSettings.loading')}</p>
        ) : (
          <Tabs
            value={tab}
            onValueChange={setTab}
            className="flex w-full max-w-full flex-col"
          >
            <TabsList className="grid w-full shrink-0 grid-cols-2 sm:grid-cols-4">
              <TabsTrigger value="server">{t('pacsSettings.tabs.server')}</TabsTrigger>
              <TabsTrigger value="equipment">{t('pacsSettings.tabs.equipment')}</TabsTrigger>
              <TabsTrigger value="worklist">{t('pacsSettings.tabs.worklist')}</TabsTrigger>
              <TabsTrigger value="admin">{t('pacsSettings.tabs.admin')}</TabsTrigger>
            </TabsList>

            <TabsContent
              value="server"
              className="mt-3 flex w-full max-w-full flex-col gap-4 data-[state=inactive]:hidden"
            >
              {statsLoading && !pacsStats ? (
                <p className="text-muted-foreground text-sm">{t('pacsSettings.loadingStats')}</p>
              ) : pacsStats ? (
                <div className="border-border rounded-lg border p-3">
                  <PacsStatsPanel
                    stats={pacsStats}
                    compact={!expanded}
                  />
                </div>
              ) : null}

              <div className="border-border rounded-lg border p-3">
                <p className="mb-3 text-sm font-medium">{t('pacsSettings.dicomConfig')}</p>
                <div className="flex flex-col gap-3">
                  <label className="flex flex-col gap-1 text-sm">
                    {t('pacsSettings.institutionName')}
                    <Input
                      value={institutionName}
                      onChange={e => setInstitutionName(e.target.value)}
                      maxLength={64}
                    />
                  </label>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <label className="flex flex-col gap-1 text-sm">
                      {t('pacsSettings.aeTitle')}
                      <Input
                        value={dicomAet}
                        onChange={e => setDicomAet(e.target.value.toUpperCase())}
                        maxLength={16}
                      />
                    </label>
                    <label className="text-muted-foreground flex flex-col gap-1 text-sm">
                      {t('pacsSettings.dicomPort')}
                      <Input
                        value={dicomPort}
                        readOnly
                        disabled
                      />
                    </label>
                  </div>
                  <p className="text-muted-foreground text-xs">{t('pacsSettings.dicomPortNote')}</p>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={checkCalledAet}
                      onChange={e => setCheckCalledAet(e.target.checked)}
                    />
                    {t('pacsSettings.checkCalledAet')}
                  </label>
                  <div className="flex justify-end">
                    <Button
                      onClick={handleSaveServer}
                      disabled={saving}
                    >
                      {t('pacsSettings.saveServer')}
                    </Button>
                  </div>
                </div>
              </div>
            </TabsContent>

            <TabsContent
              value="equipment"
              className="mt-3 flex w-full max-w-full flex-col gap-3 data-[state=inactive]:hidden"
            >
              {equipment.map((item, index) => (
                <div
                  key={item.id || index}
                  className="border-border flex flex-col gap-2 rounded border p-3"
                >
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    <Input
                      placeholder={t('pacsSettings.aeTitle')}
                      value={item.aet}
                      onChange={e => updateEquipment(index, { aet: e.target.value.toUpperCase() })}
                    />
                    <Input
                      placeholder={t('pacsSettings.placeholders.modality')}
                      value={item.modality}
                      onChange={e =>
                        updateEquipment(index, { modality: e.target.value.toUpperCase() })
                      }
                    />
                    <Input
                      placeholder={t('pacsSettings.placeholders.host')}
                      value={item.host}
                      onChange={e => updateEquipment(index, { host: e.target.value })}
                    />
                    <Input
                      placeholder={t('pacsSettings.port')}
                      type="number"
                      value={item.port}
                      onChange={e => updateEquipment(index, { port: Number(e.target.value) || 104 })}
                    />
                  </div>
                  <Input
                    placeholder={t('pacsSettings.placeholders.equipmentDescription')}
                    value={item.description}
                    onChange={e => updateEquipment(index, { description: e.target.value })}
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    className="self-end"
                    onClick={() => setEquipment(prev => prev.filter((_, i) => i !== index))}
                  >
                    {t('pacsSettings.remove')}
                  </Button>
                </div>
              ))}
              <Button
                variant="outline"
                onClick={() => setEquipment(prev => [...prev, emptyEquipment()])}
              >
                {t('pacsSettings.addEquipment')}
              </Button>
              <div className="flex justify-end">
                <Button
                  onClick={handleSaveEquipment}
                  disabled={saving}
                >
                  {t('pacsSettings.saveEquipment')}
                </Button>
              </div>
            </TabsContent>

            <TabsContent
              value="worklist"
              className="mt-3 flex w-full max-w-full flex-col gap-3 data-[state=inactive]:hidden"
            >
              <p className="text-muted-foreground text-xs">{t('pacsSettings.worklistHint')}</p>
              {views.map((view, index) => (
                <div
                  key={view.id}
                  className="border-border flex flex-col gap-2 rounded border p-3"
                >
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    <Input
                      placeholder={t('pacsSettings.placeholders.viewId')}
                      value={view.id}
                      onChange={e => updateView(index, { id: e.target.value })}
                    />
                    <Input
                      placeholder={t('pacsSettings.placeholders.viewLabel')}
                      value={view.label}
                      onChange={e => updateView(index, { label: e.target.value })}
                    />
                  </div>
                  <Input
                    placeholder={t('pacsSettings.placeholders.viewModalities')}
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
                    placeholder={t('pacsSettings.placeholders.viewDescription')}
                    value={view.description}
                    onChange={e => updateView(index, { description: e.target.value })}
                  />
                  <Input
                    placeholder={t('pacsSettings.placeholders.stationAetFuture')}
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
                  {t('pacsSettings.saveViews')}
                </Button>
              </div>
            </TabsContent>

            <TabsContent
              value="admin"
              className="mt-3 flex w-full max-w-full flex-col gap-3 data-[state=inactive]:hidden"
            >
              {adminLoading ? (
                <p className="text-sm">{t('pacsSettings.loadingAdmin')}</p>
              ) : mwlStatus ? (
                <>
                  {pacsStats ? (
                    <div className="border-border rounded-lg border p-3">
                      <PacsStatsPanel stats={pacsStats} />
                    </div>
                  ) : null}

                  <div className="border-border rounded border p-3 text-sm">
                    <p className="font-medium">{t('pacsSettings.backup')}</p>
                    {backupStatus ? (
                      <>
                        <p className="text-muted-foreground mt-1 text-xs">
                          {t('pacsSettings.lastBackup')}{' '}
                          {backupStatus.last_at
                            ? formatTs(backupStatus.last_at, i18n.language)
                            : t('pacsSettings.noBackup')}
                          {backupStatus.last_path ? ` (${backupStatus.last_path})` : ''}
                        </p>
                        <p className="text-muted-foreground text-xs">
                          {t('pacsSettings.backupSchedule', {
                            hours: backupStatus.interval_hours,
                            daily: backupStatus.retention_daily ?? backupStatus.retention_days,
                            weekly: backupStatus.retention_weekly ?? 4,
                          })}
                          {backupStatus.configured && backupStatus.success
                            ? t('pacsSettings.backupOk')
                            : backupStatus.configured
                              ? t('pacsSettings.backupFailed')
                              : t('pacsSettings.backupEnable')}
                        </p>
                      </>
                    ) : (
                      <p className="text-muted-foreground mt-1 text-xs">
                        {t('pacsSettings.loadingBackupStatus')}
                      </p>
                    )}
                  </div>

                  <div className="border-border rounded border p-3 text-sm">
                    <p className="font-medium">{t('pacsSettings.mwlStatus')}</p>
                    <p className="text-muted-foreground mt-1 text-xs">
                      {t('pacsSettings.mwlPlugin')}{' '}
                      {mwlStatus.plugin_enabled
                        ? t('pacsSettings.mwlActive')
                        : t('pacsSettings.mwlInactive')}{' '}
                      · {t('pacsSettings.mwlEntries')} {mwlStatus.entries_total}
                    </p>
                    <p className="text-muted-foreground text-xs">
                      {t('pacsSettings.mwlLastSync')}{' '}
                      {formatTs(mwlStatus.sync.last_at, i18n.language)} {t('pacsSettings.mwlBy')}{' '}
                      {mwlStatus.sync.last_actor || '—'} ({mwlStatus.sync.last_synced}{' '}
                      {t('pacsSettings.mwlFiles')})
                    </p>
                    {mwlStatus.sync.last_error ? (
                      <p className="text-destructive mt-1 text-xs">
                        {t('pacsSettings.mwlLastError')} {mwlStatus.sync.last_error}
                      </p>
                    ) : null}
                    <div className="mt-2 flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        onClick={handleMwlSync}
                        disabled={saving || !mwlSql.enabled}
                      >
                        {t('pacsSettings.mwlSyncNow')}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void loadAdminData()}
                        disabled={saving}
                      >
                        {t('pacsSettings.mwlRefresh')}
                      </Button>
                    </div>
                  </div>

                  <div className="border-border rounded border p-3">
                    <p className="mb-2 text-sm font-medium">{t('pacsSettings.sqlConnection')}</p>
                    {!isAdmin ? (
                      <p className="text-muted-foreground text-xs">
                        {t('pacsSettings.sqlReadonly', {
                          host: mwlSql.host,
                          port: mwlSql.port,
                          database: mwlSql.database,
                          table: mwlSql.table,
                          minutes: mwlSql.sync_interval_minutes,
                          disabled: mwlSql.enabled ? '' : t('pacsSettings.sqlDisabled'),
                        })}
                      </p>
                    ) : (
                      <div className="flex flex-col gap-2">
                        <label className="flex items-center gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={mwlSql.enabled}
                            onChange={e => setMwlSql(prev => ({ ...prev, enabled: e.target.checked }))}
                          />
                          {t('pacsSettings.sqlEnabled')}
                        </label>
                        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.host')}
                            <Input
                              value={mwlSql.host}
                              onChange={e => setMwlSql(prev => ({ ...prev, host: e.target.value }))}
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.port')}
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
                            {t('pacsSettings.sqlDatabase')}
                            <Input
                              value={mwlSql.database}
                              onChange={e =>
                                setMwlSql(prev => ({ ...prev, database: e.target.value }))
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.sqlUser')}
                            <Input
                              value={mwlSql.username}
                              onChange={e =>
                                setMwlSql(prev => ({ ...prev, username: e.target.value }))
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.sqlTable')}
                            <Input
                              value={mwlSql.table}
                              onChange={e => setMwlSql(prev => ({ ...prev, table: e.target.value }))}
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.sqlPasswordEnv')}
                            <Input
                              value={mwlSql.password_env}
                              onChange={e =>
                                setMwlSql(prev => ({ ...prev, password_env: e.target.value }))
                              }
                              placeholder={t('pacsSettings.placeholders.postgresPassword')}
                            />
                          </label>
                          <label className="col-span-1 flex flex-col gap-1 text-xs sm:col-span-2">
                            {t('pacsSettings.sqlInterval')}
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
                          {t('pacsSettings.sqlPasswordStatus', { env: mwlSql.password_env })}{' '}
                          {mwlSql.password_configured
                            ? t('pacsSettings.sqlPasswordSet')
                            : t('pacsSettings.sqlPasswordMissing')}
                        </p>
                        <div className="flex justify-end">
                          <Button
                            size="sm"
                            onClick={handleSaveMwlSql}
                            disabled={saving}
                          >
                            {t('pacsSettings.saveSql')}
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="border-border rounded border p-3">
                    <p className="mb-2 text-sm font-medium">{t('pacsSettings.mwlPreview')}</p>
                    {mwlEntries.length === 0 ? (
                      <p className="text-muted-foreground text-xs">
                        {t('pacsSettings.mwlNoEntriesScheduled')}
                      </p>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full min-w-[320px] text-left text-xs">
                          <thead>
                            <tr className="text-muted-foreground border-b">
                              <th className="py-1 pr-2">{t('pacsSettings.mwlAccession')}</th>
                              <th className="py-1 pr-2">{t('pacsSettings.mwlPatient')}</th>
                              <th className="py-1 pr-2">{t('pacsSettings.mwlModShort')}</th>
                              <th className="py-1">{t('pacsSettings.mwlStation')}</th>
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
                      </div>
                    )}
                  </div>

                  {isAdmin ? (
                    <div className="border-border rounded border p-3">
                      <p className="mb-2 text-sm font-medium">{t('pacsSettings.auditTitle')}</p>
                      {auditEvents.length === 0 ? (
                        <p className="text-muted-foreground text-xs">{t('pacsSettings.auditEmpty')}</p>
                      ) : (
                        <div className="overflow-x-auto">
                          <table className="w-full min-w-[320px] text-left text-xs">
                            <thead>
                              <tr className="text-muted-foreground border-b">
                                <th className="py-1 pr-2">{t('pacsSettings.auditWhen')}</th>
                                <th className="py-1 pr-2">{t('pacsSettings.auditEvent')}</th>
                                <th className="py-1">{t('pacsSettings.auditUser')}</th>
                              </tr>
                            </thead>
                            <tbody>
                              {auditEvents.map((item, index) => (
                                <tr
                                  key={`${item.timestamp}-${index}`}
                                  className="border-border/60 border-b"
                                >
                                  <td className="py-1 pr-2 whitespace-nowrap">
                                    {formatTs(item.timestamp, i18n.language)}
                                  </td>
                                  <td className="py-1 pr-2">{item.event}</td>
                                  <td className="py-1">{item.actor}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-muted-foreground text-xs">{t('pacsSettings.auditAdminOnly')}</p>
                  )}
                </>
              ) : (
                <Button
                  variant="outline"
                  onClick={() => void loadAdminData()}
                >
                  {t('pacsSettings.loadAdmin')}
                </Button>
              )}
            </TabsContent>
          </Tabs>
        )}
      </div>

      {error ? <p className="text-destructive shrink-0 text-sm">{error}</p> : null}
      {message ? <p className="text-primary shrink-0 text-sm">{message}</p> : null}

      <div className="flex shrink-0 justify-end gap-2 border-t pt-2">
        {expanded ? (
          <Button
            variant="outline"
            onClick={() => setExpanded(false)}
          >
            {t('pacsSettings.reduceWindow')}
          </Button>
        ) : null}
        <Button
          variant="ghost"
          onClick={() => {
            setExpanded(false);
            hide?.();
          }}
          disabled={saving}
        >
          {t('pacsSettings.close')}
        </Button>
      </div>
    </>
  );

  if (expanded) {
    return createPortal(
      <div className="fixed inset-0 z-[200] flex flex-col bg-muted p-3 sm:p-5">
        <div className="mb-3 flex shrink-0 items-center justify-between gap-3">
          <h2 className="text-primary text-lg font-semibold">
            {t('workList.settings.modalTitle')}
          </h2>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setExpanded(false)}
          >
            {t('pacsSettings.reduceWindow')}
          </Button>
        </div>
        <div className="text-foreground flex min-h-0 flex-1 flex-col gap-2 overflow-hidden">
          {panelBody}
        </div>
      </div>,
      document.body
    );
  }

  return (
    <div className="text-foreground flex h-[min(72vh,720px)] min-h-[380px] w-full max-w-full flex-col gap-2 overflow-hidden">
      {panelBody}
    </div>
  );
}

export default PacsSettingsModal;
