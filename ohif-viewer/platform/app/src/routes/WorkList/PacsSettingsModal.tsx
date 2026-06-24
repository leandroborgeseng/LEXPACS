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
  driver: string;
  mode: 'table' | 'custom';
  host: string;
  port: number;
  database: string;
  username: string;
  password_env: string;
  table: string;
  custom_sql: string;
  field_mapping: Record<string, string>;
  modality_filter: string[];
  modality_routes: { modality: string; station_aet: string }[];
  sync_interval_minutes: number;
  password_configured: boolean;
  available_drivers?: { id: string; label: string; default_port: number }[];
};

const MWL_MAP_FIELDS = [
  'accession_number',
  'patient_id',
  'patient_name',
  'modality',
  'station_aet',
  'procedure_description',
  'scheduled_date',
] as const;

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

type Hl7Config = {
  enabled: boolean;
  listen_host: string;
  listen_port: number;
  auto_sync: boolean;
  map_modality_to_station: boolean;
  default_station_aet: string;
  sending_application: string;
  sending_facility: string;
};

type Hl7Status = {
  config: Hl7Config;
  stats: {
    messages_total: number;
    last_at: string;
    last_accession: string;
    last_control: string;
    last_error: string;
  };
};

type AdGroupMapping = {
  ad_group_cn: string;
  lex_group: string;
};

type AdConfig = {
  enabled: boolean;
  connection_url: string;
  use_ssl: boolean;
  bind_dn: string;
  bind_password_env: string;
  users_dn: string;
  groups_dn: string;
  username_ldap_attribute: string;
  import_users: boolean;
  group_mappings: AdGroupMapping[];
  full_sync_period_hours: number;
  changed_sync_period_hours: number;
  bind_password_configured: boolean;
  keycloak_realm: string;
  keycloak_configured: boolean;
};

type AdSyncMeta = {
  last_at: string;
  last_actor: string;
  users_imported: number;
  groups_mapped: number;
  memberships_applied: number;
  last_error: string;
  provider_configured: boolean;
  connection_ok: boolean;
};

type AdStatus = {
  config: AdConfig;
  sync: AdSyncMeta;
  lex_groups: string[];
};

type MppsConfig = {
  enabled: boolean;
  listen_host: string;
  listen_port: number;
  aet: string;
  auto_complete_mwl: boolean;
  complete_on_discontinued: boolean;
};

type MppsStatus = {
  config: MppsConfig;
  stats: {
    messages_total: number;
    completed_total: number;
    mwl_removed_total: number;
    last_at: string;
    last_accession: string;
    last_status: string;
    last_actor: string;
    last_error: string;
  };
  server_running: boolean;
};

type QrConsumer = {
  key: string;
  aet: string;
  host: string;
  allow_find: boolean;
  allow_move: boolean;
  allow_get: boolean;
};

type QrStatus = {
  dicom_aet: string;
  dicom_port: number;
  orthanc: {
    query_retrieve_size: number;
    dicom_always_allow_move: boolean;
    dicom_always_allow_get: boolean;
    dicom_always_allow_find: boolean;
  };
  config: {
    query_retrieve_size: number;
    smoke_consumer_aet: string;
    smoke_consumer_host: string;
  };
  stats: {
    last_at: string;
    last_actor: string;
    last_find_count: number;
    last_error: string;
    last_success: boolean;
  };
  consumers: QrConsumer[];
  consumer_count: number;
  qr_ready: boolean;
};

type DicomTlsStatus = {
  config: {
    enabled: boolean;
    remote_certificate_required: boolean;
    smoke_consumer_aet: string;
    min_protocol_version: number;
  };
  stats: {
    last_at: string;
    last_actor: string;
    last_success: boolean;
    last_error: string;
    generated_at: string;
    generated_by: string;
  };
  orthanc: {
    enabled: boolean;
    remote_certificate_required: boolean;
    certificate: string;
    trusted_certificates: string;
  };
  certificates: {
    ready: boolean;
    server_present: boolean;
    directory: string;
    server_certificate: string;
    trusted_certificates: string;
  };
  dicom_aet: string;
  dicom_port: number;
  tls_ready: boolean;
};

type PortalOps = {
  backup_interval_hours: number;
  backup_retention_daily: number;
  backup_retention_weekly: number;
  backup_retention_days: number;
  login_rate_limit_attempts: number;
  login_rate_limit_window_seconds: number;
};

const INGEST_OPTIONS = [
  { value: '', labelKey: 'pacsSettings.ingestNone' },
  { value: '1.2.840.10008.1.2.4.80', labelKey: 'pacsSettings.ingestJpegLs' },
  { value: '1.2.840.10008.1.2.4.70', labelKey: 'pacsSettings.ingestJpegLossless' },
  { value: '1.2.840.10008.1.2', labelKey: 'pacsSettings.ingestExplicit' },
] as const;

const emptyHl7Config = (): Hl7Config => ({
  enabled: true,
  listen_host: '0.0.0.0',
  listen_port: 2575,
  auto_sync: true,
  map_modality_to_station: true,
  default_station_aet: '',
  sending_application: 'LEXPACS',
  sending_facility: 'LEX',
});

const emptyMppsConfig = (): MppsConfig => ({
  enabled: true,
  listen_host: '0.0.0.0',
  listen_port: 4243,
  aet: 'LEXMPPS',
  auto_complete_mwl: true,
  complete_on_discontinued: false,
});

const emptyDicomTlsConfig = () => ({
  enabled: false,
  remote_certificate_required: false,
  smoke_consumer_aet: 'LEXTLS',
  min_protocol_version: 0,
});

const emptyAdConfig = (): AdConfig => ({
  enabled: false,
  connection_url: 'ldap://dc01.example.local:389',
  use_ssl: false,
  bind_dn: '',
  bind_password_env: 'AD_BIND_PASSWORD',
  users_dn: '',
  groups_dn: '',
  username_ldap_attribute: 'sAMAccountName',
  import_users: true,
  group_mappings: [
    { ad_group_cn: 'LEX-Radiologistas', lex_group: 'radiologista' },
    { ad_group_cn: 'LEX-Tecnicos', lex_group: 'tecnico' },
    { ad_group_cn: 'LEX-Admins', lex_group: 'admin' },
  ],
  full_sync_period_hours: 24,
  changed_sync_period_hours: 1,
  bind_password_configured: false,
  keycloak_realm: 'lex-pacs',
  keycloak_configured: false,
});

const emptyPortalOps = (): PortalOps => ({
  backup_interval_hours: 24,
  backup_retention_daily: 7,
  backup_retention_weekly: 4,
  backup_retention_days: 14,
  login_rate_limit_attempts: 20,
  login_rate_limit_window_seconds: 60,
});

type MigrationForm = {
  source: { label: string; aet: string; host: string; port: number };
  filters: {
    study_date_from: string;
    study_date_to: string;
    patient_id: string;
    modality: string;
  };
  batch_size: number;
  pause_seconds: number;
  skip_existing: boolean;
};

type MigrationStatus = {
  config: MigrationForm;
  status: string;
  cursor: number;
  queue_total: number;
  pending: number;
  progress_percent: number;
  stats: {
    completed: number;
    failed: number;
    skipped: number;
    instances_imported: number;
  };
  last_error: string;
};

const emptyMigrationForm = (): MigrationForm => ({
  source: { label: '', aet: '', host: '', port: 104 },
  filters: { study_date_from: '', study_date_to: '', patient_id: '', modality: '' },
  batch_size: 1,
  pause_seconds: 2,
  skip_existing: true,
});

type StorageRule = {
  id: string;
  enabled: boolean;
  min_age_years: number;
  transfer_syntax: string;
  modalities: string[];
};

type StorageForm = {
  enabled: boolean;
  run_interval_hours: number;
  batch_size: number;
  pause_seconds: number;
  rules: StorageRule[];
};

type StorageStatus = StorageForm & {
  status: string;
  cursor: number;
  queue_total: number;
  pending: number;
  progress_percent: number;
  stats: {
    compressed: number;
    skipped: number;
    failed: number;
    instances: number;
  };
  last_run_at: string;
  last_error: string;
  transfer_syntax_options: { uid: string; label: string }[];
};

const emptyStorageForm = (): StorageForm => ({
  enabled: false,
  run_interval_hours: 24,
  batch_size: 5,
  pause_seconds: 2,
  rules: [],
});

function storageStatusLabel(status: string, t: (key: string) => string): string {
  const map: Record<string, string> = {
    idle: 'pacsSettings.storageStatusIdle',
    running: 'pacsSettings.storageStatusRunning',
    paused: 'pacsSettings.storageStatusPaused',
    completed: 'pacsSettings.storageStatusCompleted',
  };
  return t(map[status] || map.idle);
}

function migrationStatusLabel(status: string, t: (key: string) => string): string {
  const map: Record<string, string> = {
    idle: 'pacsSettings.migrationStatusIdle',
    discovering: 'pacsSettings.migrationStatusDiscovering',
    running: 'pacsSettings.migrationStatusRunning',
    paused: 'pacsSettings.migrationStatusPaused',
    completed: 'pacsSettings.migrationStatusCompleted',
    error: 'pacsSettings.migrationStatusError',
  };
  return t(map[status] || map.idle);
}

type PacsSettingsModalProps = {
  hide?: () => void;
  mode?: 'modal' | 'page';
};

const emptyMwlSql = (): MwlSqlForm => ({
  enabled: true,
  driver: 'postgresql',
  mode: 'table',
  host: 'database',
  port: 5432,
  database: 'orthanc',
  username: 'orthanc',
  password_env: 'POSTGRES_PASSWORD',
  table: 'lex_mwl_schedule',
  custom_sql: '',
  field_mapping: Object.fromEntries(MWL_MAP_FIELDS.map(f => [f, f])),
  modality_filter: [],
  modality_routes: [],
  sync_interval_minutes: 5,
  password_configured: false,
});

function mwlSqlFromStatus(sql: MwlStatus['sql'] & Partial<MwlSqlForm>): MwlSqlForm {
  const base = emptyMwlSql();
  return {
    ...base,
    enabled: sql.enabled,
    driver: sql.driver || base.driver,
    mode: (sql.mode as MwlSqlForm['mode']) || base.mode,
    host: sql.host,
    port: sql.port,
    database: sql.database,
    username: sql.username,
    password_env: sql.password_env || 'POSTGRES_PASSWORD',
    table: sql.table,
    custom_sql: sql.custom_sql || base.custom_sql,
    field_mapping: { ...base.field_mapping, ...(sql.field_mapping || {}) },
    modality_filter: Array.isArray(sql.modality_filter) ? sql.modality_filter : [],
    modality_routes: Array.isArray(sql.modality_routes) ? sql.modality_routes : [],
    sync_interval_minutes: sql.sync_interval_minutes,
    password_configured: sql.password_configured,
    available_drivers: sql.available_drivers,
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

export function PacsSettingsModal({ hide, mode = 'modal' }: PacsSettingsModalProps) {
  const { t, i18n } = useTranslation('LexPacs');
  const isPage = mode === 'page';
  const [tab, setTab] = useState('server');
  const [expanded, setExpanded] = useState(false);
  const isExpanded = isPage || expanded;
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [statsLoading, setStatsLoading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const [dicomAet, setDicomAet] = useState('');
  const [dicomPort, setDicomPort] = useState('');
  const [institutionName, setInstitutionName] = useState('');
  const [checkCalledAet, setCheckCalledAet] = useState(true);
  const [checkModalityHost, setCheckModalityHost] = useState(true);
  const [restrictInbound, setRestrictInbound] = useState(true);
  const [inboundWarning, setInboundWarning] = useState(false);
  const [ingestTranscoding, setIngestTranscoding] = useState('');
  const [worklistsEnabled, setWorklistsEnabled] = useState(true);
  const [worklistsFilterIssuerAet, setWorklistsFilterIssuerAet] = useState(false);

  const [equipment, setEquipment] = useState<EquipmentItem[]>([]);
  const [views, setViews] = useState<WorklistViewItem[]>([]);

  const [isAdmin, setIsAdmin] = useState(false);
  const [integrationLoading, setIntegrationLoading] = useState(false);
  const [opsLoading, setOpsLoading] = useState(false);
  const [mwlStatus, setMwlStatus] = useState<MwlStatus | null>(null);
  const [mwlEntries, setMwlEntries] = useState<MwlEntry[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [mwlSql, setMwlSql] = useState<MwlSqlForm>(emptyMwlSql);
  const [pacsStats, setPacsStats] = useState<PacsStats | null>(null);
  const [backupStatus, setBackupStatus] = useState<BackupStatus | null>(null);
  const [hl7Status, setHl7Status] = useState<Hl7Status | null>(null);
  const [hl7Config, setHl7Config] = useState<Hl7Config>(emptyHl7Config);
  const [hl7TestMessage, setHl7TestMessage] = useState('');
  const [hl7TestApply, setHl7TestApply] = useState(true);
  const [adStatus, setAdStatus] = useState<AdStatus | null>(null);
  const [adConfig, setAdConfig] = useState<AdConfig>(emptyAdConfig);
  const [mppsStatus, setMppsStatus] = useState<MppsStatus | null>(null);
  const [mppsConfig, setMppsConfig] = useState<MppsConfig>(emptyMppsConfig);
  const [qrStatus, setQrStatus] = useState<QrStatus | null>(null);
  const [qrTesting, setQrTesting] = useState(false);
  const [dicomTlsStatus, setDicomTlsStatus] = useState<DicomTlsStatus | null>(null);
  const [dicomTlsConfig, setDicomTlsConfig] = useState(emptyDicomTlsConfig);
  const [dicomTlsSaving, setDicomTlsSaving] = useState(false);
  const [dicomTlsTesting, setDicomTlsTesting] = useState(false);
  const [portalOps, setPortalOps] = useState<PortalOps>(emptyPortalOps);
  const [migrationLoading, setMigrationLoading] = useState(false);
  const [migrationStatus, setMigrationStatus] = useState<MigrationStatus | null>(null);
  const [migrationForm, setMigrationForm] = useState<MigrationForm>(emptyMigrationForm);
  const [storageLoading, setStorageLoading] = useState(false);
  const [storageStatus, setStorageStatus] = useState<StorageStatus | null>(null);
  const [storageForm, setStorageForm] = useState<StorageForm>(emptyStorageForm);
  const [worklistLoading, setWorklistLoading] = useState(false);
  const [mwlPreview, setMwlPreview] = useState<MwlEntry[]>([]);

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

  const loadIntegrationData = useCallback(async () => {
    setIntegrationLoading(true);
    setError('');
    try {
      const [meRes, statusRes, entriesRes, hl7Res, adRes, mppsRes, qrRes] = await Promise.all([
        fetch(AUTH_ME, { credentials: 'include' }),
        fetch(`${API_BASE}/mwl/status`, { credentials: 'include' }),
        fetch(`${API_BASE}/mwl/entries`, { credentials: 'include' }),
        fetch(`${API_BASE}/hl7/status`, { credentials: 'include' }),
        fetch(`${API_BASE}/ad/status`, { credentials: 'include' }),
        fetch(`${API_BASE}/mpps/status`, { credentials: 'include' }),
        fetch(`${API_BASE}/qr/status`, { credentials: 'include' }),
      ]);
      const me = await meRes.json().catch(() => ({}));
      const status = await statusRes.json().catch(() => null);
      const entriesData = await entriesRes.json().catch(() => ({}));
      const hl7Data = await hl7Res.json().catch(() => null);
      const adData = await adRes.json().catch(() => null);
      const mppsData = await mppsRes.json().catch(() => null);
      const qrData = await qrRes.json().catch(() => null);

      const permissions = me.permissions as { can_admin?: boolean } | undefined;
      setIsAdmin(Boolean(permissions?.can_admin));

      if (!statusRes.ok) {
        throw new Error(status?.detail || t('pacsSettings.errors.loadMwl'));
      }
      setMwlStatus(status);
      setMwlSql(mwlSqlFromStatus(status.sql));
      setMwlEntries(Array.isArray(entriesData.entries) ? entriesData.entries.slice(0, 20) : []);
      if (hl7Res.ok && hl7Data) {
        const hl7 = hl7Data as Hl7Status;
        setHl7Status(hl7);
        setHl7Config({ ...emptyHl7Config(), ...hl7.config });
      }
      if (adRes.ok && adData) {
        const ad = adData as AdStatus;
        setAdStatus(ad);
        setAdConfig({ ...emptyAdConfig(), ...ad.config });
      }
      if (mppsRes.ok && mppsData) {
        const mpps = mppsData as MppsStatus;
        setMppsStatus(mpps);
        setMppsConfig({ ...emptyMppsConfig(), ...mpps.config });
      }
      if (qrRes.ok && qrData) {
        setQrStatus(qrData as QrStatus);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.loadIntegration'));
    } finally {
      setIntegrationLoading(false);
    }
  }, [t]);

  const loadOpsData = useCallback(async () => {
    setOpsLoading(true);
    setError('');
    try {
      const [meRes, opsRes] = await Promise.all([
        fetch(AUTH_ME, { credentials: 'include' }),
        fetch(`${API_BASE}/portal-ops`, { credentials: 'include' }),
      ]);
      const me = await meRes.json().catch(() => ({}));
      const opsData = await opsRes.json().catch(() => null);

      const permissions = me.permissions as { can_admin?: boolean } | undefined;
      const admin = Boolean(permissions?.can_admin);
      setIsAdmin(admin);

      if (opsRes.ok && opsData) {
        setPortalOps({ ...emptyPortalOps(), ...opsData });
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
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.loadAdmin'));
    } finally {
      setOpsLoading(false);
    }
  }, [t]);

  const loadStorageData = useCallback(async () => {
    setStorageLoading(true);
    setError('');
    try {
      const [meRes, backupRes, opsRes, storageRes] = await Promise.all([
        fetch(AUTH_ME, { credentials: 'include' }),
        fetch(`${API_BASE}/backup/status`, { credentials: 'include' }),
        fetch(`${API_BASE}/portal-ops`, { credentials: 'include' }),
        fetch(`${API_BASE}/storage/status`, { credentials: 'include' }),
      ]);
      const me = await meRes.json().catch(() => ({}));
      const backupData = await backupRes.json().catch(() => null);
      const opsData = await opsRes.json().catch(() => null);
      const storageData = await storageRes.json().catch(() => null);

      const permissions = me.permissions as { can_admin?: boolean } | undefined;
      setIsAdmin(Boolean(permissions?.can_admin));

      if (backupRes.ok && backupData) {
        setBackupStatus(backupData as BackupStatus);
      }
      if (opsRes.ok && opsData) {
        setPortalOps({ ...emptyPortalOps(), ...opsData });
      }
      if (!storageRes.ok) {
        throw new Error(storageData?.detail || t('pacsSettings.errors.loadStorage'));
      }
      const status = storageData as StorageStatus;
      setStorageStatus(status);
      setStorageForm({
        enabled: status.enabled,
        run_interval_hours: status.run_interval_hours,
        batch_size: status.batch_size,
        pause_seconds: status.pause_seconds,
        rules: Array.isArray(status.rules) ? status.rules : [],
      });
      await loadStats();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.loadStorage'));
    } finally {
      setStorageLoading(false);
    }
  }, [loadStats, t]);

  const loadMigrationData = useCallback(async () => {
    setMigrationLoading(true);
    setError('');
    try {
      const [meRes, statusRes] = await Promise.all([
        fetch(AUTH_ME, { credentials: 'include' }),
        fetch(`${API_BASE}/migration/status`, { credentials: 'include' }),
      ]);
      const me = await meRes.json().catch(() => ({}));
      const statusData = await statusRes.json().catch(() => null);
      setIsAdmin(Boolean((me.permissions as { can_admin?: boolean })?.can_admin));
      if (!statusRes.ok) {
        throw new Error(statusData?.detail || t('pacsSettings.errors.loadMigration'));
      }
      const data = statusData as MigrationStatus;
      setMigrationStatus(data);
      setMigrationForm({ ...emptyMigrationForm(), ...data.config });
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.loadMigration'));
    } finally {
      setMigrationLoading(false);
    }
  }, [t]);

  const loadWorklistData = useCallback(async () => {
    setWorklistLoading(true);
    setError('');
    try {
      const [meRes, sqlRes, statusRes] = await Promise.all([
        fetch(AUTH_ME, { credentials: 'include' }),
        fetch(`${API_BASE}/mwl-sql`, { credentials: 'include' }),
        fetch(`${API_BASE}/mwl/status`, { credentials: 'include' }),
      ]);
      const me = await meRes.json().catch(() => ({}));
      const sqlData = await sqlRes.json().catch(() => null);
      const status = await statusRes.json().catch(() => null);
      setIsAdmin(Boolean((me.permissions as { can_admin?: boolean })?.can_admin));
      if (sqlRes.ok && sqlData) {
        setMwlSql(mwlSqlFromStatus(sqlData));
      }
      if (statusRes.ok && status) {
        setMwlStatus(status);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.loadMwl'));
    } finally {
      setWorklistLoading(false);
    }
  }, [t]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [settingsRes, equipmentRes, viewsRes, tlsRes] = await Promise.all([
          fetch(`${API_BASE}/settings`, { credentials: 'include' }),
          fetch(`${API_BASE}/equipment`, { credentials: 'include' }),
          fetch(`${API_BASE}/worklist-views`, { credentials: 'include' }),
          fetch(`${API_BASE}/dicom-tls/status`, { credentials: 'include' }),
        ]);
        const settings = await settingsRes.json().catch(() => ({}));
        const equipmentData = await equipmentRes.json().catch(() => ({}));
        const viewsData = await viewsRes.json().catch(() => ({}));
        const tlsData = await tlsRes.json().catch(() => null);
        if (!settingsRes.ok) {
          throw new Error(settings.detail || t('pacsSettings.errors.loadSettings'));
        }
        if (!cancelled) {
          setDicomAet(settings.dicom_aet || '');
          setDicomPort(String(settings.dicom_port || ''));
          setInstitutionName(settings.name || '');
          setCheckCalledAet(Boolean(settings.dicom_check_called_aet));
          setCheckModalityHost(Boolean(settings.dicom_check_modality_host));
          setRestrictInbound(Boolean(settings.dicom_restrict_inbound));
          setInboundWarning(Boolean(settings.dicom_inbound_open_warning));
          setIngestTranscoding(settings.ingest_transcoding || '');
          setWorklistsEnabled(settings.worklists_enabled !== false);
          setWorklistsFilterIssuerAet(Boolean(settings.worklists_filter_issuer_aet));
          setEquipment(Array.isArray(equipmentData.items) ? equipmentData.items : []);
          setViews(Array.isArray(viewsData.views) ? viewsData.views : []);
          if (tlsRes.ok && tlsData) {
            const tls = tlsData as DicomTlsStatus;
            setDicomTlsStatus(tls);
            setDicomTlsConfig({ ...emptyDicomTlsConfig(), ...tls.config });
          }
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
    if (tab === 'integration') {
      void loadIntegrationData();
    }
    if (tab === 'ops') {
      void loadOpsData();
    }
    if (tab === 'storage') {
      void loadStorageData();
    }
    if (tab === 'migration') {
      void loadMigrationData();
    }
    if (tab === 'worklist') {
      void loadWorklistData();
    }
  }, [tab, loadIntegrationData, loadOpsData, loadStorageData, loadMigrationData, loadWorklistData]);

  useEffect(() => {
    if (tab !== 'storage' || storageStatus?.status !== 'running') {
      return;
    }
    const timer = window.setInterval(() => {
      void loadStorageData();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [tab, storageStatus?.status, loadStorageData]);

  useEffect(() => {
    if (tab !== 'migration' || migrationStatus?.status !== 'running') {
      return;
    }
    const timer = window.setInterval(() => {
      void loadMigrationData();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [tab, migrationStatus?.status, loadMigrationData]);

  useEffect(() => {
    if (!expanded || isPage) {
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
  }, [expanded, isPage]);

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
          dicom_check_modality_host: checkModalityHost,
          dicom_restrict_inbound: restrictInbound,
          ingest_transcoding: ingestTranscoding,
          worklists_enabled: worklistsEnabled,
          worklists_filter_issuer_aet: worklistsFilterIssuerAet,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || t('pacsSettings.errors.save'));
      }
      setMessage(data.message || t('pacsSettings.messages.serverSaved'));
      setInboundWarning(Boolean(data.dicom_inbound_open_warning));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.save'));
    } finally {
      setSaving(false);
    }
  };

  const reloadDicomTlsStatus = async () => {
    const tlsRes = await fetch(`${API_BASE}/dicom-tls/status`, { credentials: 'include' });
    const tlsData = await tlsRes.json().catch(() => null);
    if (tlsRes.ok && tlsData) {
      const tls = tlsData as DicomTlsStatus;
      setDicomTlsStatus(tls);
      setDicomTlsConfig({ ...emptyDicomTlsConfig(), ...tls.config });
    }
  };

  const handleSaveDicomTls = async () => {
    if (!isAdmin) {
      return;
    }
    setDicomTlsSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/dicom-tls/config`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dicomTlsConfig),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || t('pacsSettings.errors.saveDicomTls'));
      }
      setDicomTlsConfig({ ...emptyDicomTlsConfig(), ...data });
      setMessage(t('pacsSettings.messages.dicomTlsSaved'));
      await reloadDicomTlsStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.saveDicomTls'));
    } finally {
      setDicomTlsSaving(false);
    }
  };

  const handleGenerateDicomTlsCerts = async () => {
    if (!isAdmin) {
      return;
    }
    setDicomTlsSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/dicom-tls/generate`, {
        method: 'POST',
        credentials: 'include',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || t('pacsSettings.errors.generateDicomTls'));
      }
      const tls = data as DicomTlsStatus;
      setDicomTlsStatus(tls);
      setDicomTlsConfig({ ...emptyDicomTlsConfig(), ...tls.config });
      setMessage(t('pacsSettings.messages.dicomTlsGenerated'));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.generateDicomTls'));
    } finally {
      setDicomTlsSaving(false);
    }
  };

  const handleTestDicomTlsEcho = async () => {
    if (!isAdmin) {
      return;
    }
    setDicomTlsTesting(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/dicom-tls/test-echo`, {
        method: 'POST',
        credentials: 'include',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || data.error || t('pacsSettings.errors.dicomTlsTest'));
      }
      if (!data.success) {
        throw new Error(data.error || t('pacsSettings.errors.dicomTlsTest'));
      }
      setMessage(
        t('pacsSettings.messages.dicomTlsTestOk', {
          aet: data.calling_aet || '—',
        })
      );
      await reloadDicomTlsStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.dicomTlsTest'));
    } finally {
      setDicomTlsTesting(false);
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
      await loadIntegrationData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.mwlSync'));
    } finally {
      setSaving(false);
    }
  };

  const handleSaveAd = async () => {
    if (!isAdmin) {
      return;
    }
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/ad/config`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(adConfig),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || t('pacsSettings.errors.saveAd'));
      }
      setAdConfig({ ...emptyAdConfig(), ...data });
      setMessage(t('pacsSettings.messages.adSaved'));
      await loadIntegrationData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.saveAd'));
    } finally {
      setSaving(false);
    }
  };

  const handleAdTest = async () => {
    if (!isAdmin) {
      return;
    }
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/ad/test`, {
        method: 'POST',
        credentials: 'include',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || t('pacsSettings.errors.adTest'));
      }
      setMessage(data.message || t('pacsSettings.messages.adTestOk'));
      await loadIntegrationData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.adTest'));
    } finally {
      setSaving(false);
    }
  };

  const handleAdSync = async () => {
    if (!isAdmin) {
      return;
    }
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/ad/sync`, {
        method: 'POST',
        credentials: 'include',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || t('pacsSettings.errors.adSync'));
      }
      setMessage(
        t('pacsSettings.messages.adSynced', {
          users: data.users_imported,
          groups: data.groups_mapped,
          memberships: data.memberships_applied,
        })
      );
      await loadIntegrationData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.adSync'));
    } finally {
      setSaving(false);
    }
  };

  const handleQrTestFind = async () => {
    if (!isAdmin) {
      return;
    }
    setQrTesting(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/qr/test-find`, {
        method: 'POST',
        credentials: 'include',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || data.error || t('pacsSettings.errors.qrTest'));
      }
      if (!data.success) {
        throw new Error(data.error || t('pacsSettings.errors.qrTest'));
      }
      setMessage(
        t('pacsSettings.messages.qrTestOk', {
          count: data.find_count ?? 0,
          aet: data.calling_aet || '—',
        })
      );
      await loadIntegrationData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.qrTest'));
    } finally {
      setQrTesting(false);
    }
  };

  const handleSaveMpps = async () => {
    if (!isAdmin) {
      return;
    }
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/mpps/config`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(mppsConfig),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || t('pacsSettings.errors.saveMpps'));
      }
      setMppsConfig({ ...emptyMppsConfig(), ...data });
      setMessage(t('pacsSettings.messages.mppsSaved'));
      await loadIntegrationData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.saveMpps'));
    } finally {
      setSaving(false);
    }
  };

  const handleSaveHl7 = async () => {
    if (!isAdmin) {
      return;
    }
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/hl7/config`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(hl7Config),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || t('pacsSettings.errors.saveHl7'));
      }
      setHl7Config({ ...emptyHl7Config(), ...data });
      setMessage(t('pacsSettings.messages.hl7Saved'));
      await loadIntegrationData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.saveHl7'));
    } finally {
      setSaving(false);
    }
  };

  const handleHl7Test = async () => {
    if (!isAdmin || !hl7TestMessage.trim()) {
      return;
    }
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/hl7/test`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: hl7TestMessage, apply: hl7TestApply }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || t('pacsSettings.errors.hl7Test'));
      }
      setMessage(t('pacsSettings.messages.hl7TestOk'));
      await loadIntegrationData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.hl7Test'));
    } finally {
      setSaving(false);
    }
  };

  const persistMwlSql = async () => {
    const response = await fetch(`${API_BASE}/mwl-sql`, {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        enabled: mwlSql.enabled,
        driver: mwlSql.driver,
        mode: mwlSql.mode,
        host: mwlSql.host.trim(),
        port: mwlSql.port,
        database: mwlSql.database.trim(),
        username: mwlSql.username.trim(),
        password_env: mwlSql.password_env.trim() || 'POSTGRES_PASSWORD',
        table: mwlSql.table.trim(),
        custom_sql: mwlSql.custom_sql,
        field_mapping: mwlSql.field_mapping,
        modality_filter: mwlSql.modality_filter,
        modality_routes: mwlSql.modality_routes,
        sync_interval_minutes: mwlSql.sync_interval_minutes,
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || t('pacsSettings.errors.saveSql'));
    }
    setMwlSql(mwlSqlFromStatus(data));
    return data;
  };

  const handleSaveMwlSql = async () => {
    if (!isAdmin) {
      return;
    }
    setSaving(true);
    setError('');
    setMessage('');
    try {
      await persistMwlSql();
      setMessage(t('pacsSettings.messages.sqlSaved'));
      await loadWorklistData();
      await loadIntegrationData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.saveSql'));
    } finally {
      setSaving(false);
    }
  };

  const handleTestMwlConnection = async () => {
    if (!isAdmin) {
      return;
    }
    setSaving(true);
    setError('');
    setMessage('');
    try {
      await persistMwlSql();
      const response = await fetch(`${API_BASE}/mwl-sql/test-connection`, {
        method: 'POST',
        credentials: 'include',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || t('pacsSettings.errors.mwlTestConnection'));
      }
      setMessage(t('pacsSettings.messages.mwlTestConnectionOk'));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.mwlTestConnection'));
    } finally {
      setSaving(false);
    }
  };

  const handlePreviewMwlSql = async () => {
    if (!isAdmin) {
      return;
    }
    setSaving(true);
    setError('');
    setMessage('');
    try {
      await persistMwlSql();
      const response = await fetch(`${API_BASE}/mwl-sql/preview`, {
        method: 'POST',
        credentials: 'include',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || t('pacsSettings.errors.mwlPreview'));
      }
      setMwlPreview(Array.isArray(data.mapped_entries) ? data.mapped_entries : []);
      setMessage(t('pacsSettings.messages.mwlPreviewOk', { count: data.mapped_entries?.length || 0 }));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.mwlPreview'));
    } finally {
      setSaving(false);
    }
  };

  const handleSavePortalOps = async () => {
    if (!isAdmin) {
      return;
    }
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/portal-ops`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(portalOps),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || t('pacsSettings.errors.saveOps'));
      }
      setPortalOps({ ...emptyPortalOps(), ...data });
      setMessage(t('pacsSettings.messages.opsSaved'));
      await loadOpsData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.saveOps'));
    } finally {
      setSaving(false);
    }
  };

  const handleSaveStorage = async () => {
    if (!isAdmin) {
      return;
    }
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const [storageRes, opsRes] = await Promise.all([
        fetch(`${API_BASE}/storage/config`, {
          method: 'PUT',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(storageForm),
        }),
        fetch(`${API_BASE}/portal-ops`, {
          method: 'PUT',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(portalOps),
        }),
      ]);
      const storageData = await storageRes.json().catch(() => ({}));
      const opsData = await opsRes.json().catch(() => ({}));
      if (!storageRes.ok) {
        throw new Error(storageData.detail || t('pacsSettings.errors.saveStorage'));
      }
      if (!opsRes.ok) {
        throw new Error(opsData.detail || t('pacsSettings.errors.saveOps'));
      }
      setPortalOps({ ...emptyPortalOps(), ...opsData });
      setMessage(t('pacsSettings.messages.storageSaved'));
      await loadStorageData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.saveStorage'));
    } finally {
      setSaving(false);
    }
  };

  const handleBackupTrigger = async () => {
    if (!isAdmin) {
      return;
    }
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/backup/trigger`, {
        method: 'POST',
        credentials: 'include',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || t('pacsSettings.errors.backupTrigger'));
      }
      setMessage(t('pacsSettings.messages.backupTriggered'));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.backupTrigger'));
    } finally {
      setSaving(false);
    }
  };

  const handleStorageAction = async (
    endpoint: string,
    okMessage: string,
    errorKey: string
  ) => {
    if (!isAdmin) {
      return;
    }
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/storage/${endpoint}`, {
        method: 'POST',
        credentials: 'include',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || t(errorKey));
      }
      setMessage(okMessage);
      await loadStorageData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t(errorKey));
    } finally {
      setSaving(false);
    }
  };

  const addStorageRule = () => {
    setStorageForm(prev => ({
      ...prev,
      rules: [
        ...prev.rules,
        {
          id: `rule-${Date.now()}`,
          enabled: true,
          min_age_years: 2,
          transfer_syntax: '1.2.840.10008.1.2.4.80',
          modalities: [],
        },
      ],
    }));
  };

  const updateStorageRule = (index: number, patch: Partial<StorageRule>) => {
    setStorageForm(prev => ({
      ...prev,
      rules: prev.rules.map((rule, i) => (i === index ? { ...rule, ...patch } : rule)),
    }));
  };

  const removeStorageRule = (index: number) => {
    setStorageForm(prev => ({
      ...prev,
      rules: prev.rules.filter((_, i) => i !== index),
    }));
  };

  const handleSaveMigration = async () => {
    if (!isAdmin) {
      return;
    }
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/migration/config`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...migrationForm,
          source: {
            ...migrationForm.source,
            aet: migrationForm.source.aet.trim().toUpperCase(),
          },
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || t('pacsSettings.errors.saveMigration'));
      }
      setMessage(t('pacsSettings.messages.migrationSaved'));
      await loadMigrationData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('pacsSettings.errors.saveMigration'));
    } finally {
      setSaving(false);
    }
  };

  const handleMigrationAction = async (
    endpoint: string,
    okMessage: string,
    errorKey: string
  ) => {
    if (!isAdmin) {
      return;
    }
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await fetch(`${API_BASE}/migration/${endpoint}`, {
        method: 'POST',
        credentials: 'include',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || t(errorKey));
      }
      if (endpoint === 'discover') {
        setMessage(t('pacsSettings.messages.migrationDiscovered', { count: data.discovered || 0 }));
      } else {
        setMessage(okMessage);
      }
      await loadMigrationData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t(errorKey));
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
    if (tab === 'integration') {
      void loadIntegrationData();
    } else if (tab === 'ops') {
      void loadOpsData();
    } else if (tab === 'storage') {
      void loadStorageData();
    } else if (tab === 'worklist') {
      void loadWorklistData();
    } else if (tab === 'migration') {
      void loadMigrationData();
    } else {
      void loadStats();
    }
  };

  const panelBody = (
    <>
      <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={refreshData}
          disabled={saving || statsLoading || integrationLoading || opsLoading || storageLoading || migrationLoading}
        >
          {statsLoading || integrationLoading || opsLoading || storageLoading || migrationLoading
            ? t('pacsSettings.refreshing')
            : t('pacsSettings.refresh')}
        </Button>
        {!isPage && !expanded ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setExpanded(true)}
          >
            {t('pacsSettings.fullscreen')}
          </Button>
        ) : null}
      </div>

      {loading ? (
        <p className="text-sm">{t('pacsSettings.loading')}</p>
      ) : (
        <Tabs
          value={tab}
          onValueChange={setTab}
          className="flex min-h-0 w-full max-w-full flex-1 flex-col"
        >
          <TabsList className="relative z-10 mb-2 inline-flex h-auto w-full flex-wrap justify-start gap-1 p-1">
            <TabsTrigger value="server">{t('pacsSettings.tabs.server')}</TabsTrigger>
              <TabsTrigger value="equipment">{t('pacsSettings.tabs.equipment')}</TabsTrigger>
              <TabsTrigger value="worklist">{t('pacsSettings.tabs.worklist')}</TabsTrigger>
              <TabsTrigger value="integration">{t('pacsSettings.tabs.integration')}</TabsTrigger>
              <TabsTrigger value="migration">{t('pacsSettings.tabs.migration')}</TabsTrigger>
              <TabsTrigger value="storage">{t('pacsSettings.tabs.storage')}</TabsTrigger>
            <TabsTrigger value="ops">{t('pacsSettings.tabs.ops')}</TabsTrigger>
          </TabsList>

          <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto overscroll-contain pr-1">
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
                    compact={!isExpanded}
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
                  <label className="flex flex-col gap-1 text-sm">
                    {t('pacsSettings.ingestTranscoding')}
                    <select
                      className="border-input bg-background rounded-md border px-3 py-2 text-sm"
                      value={ingestTranscoding}
                      onChange={e => setIngestTranscoding(e.target.value)}
                    >
                      {INGEST_OPTIONS.map(opt => (
                        <option
                          key={opt.value || 'none'}
                          value={opt.value}
                        >
                          {t(opt.labelKey)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <p className="text-muted-foreground text-xs font-medium">
                    {t('pacsSettings.mwlStatus')}
                  </p>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={worklistsEnabled}
                      onChange={e => setWorklistsEnabled(e.target.checked)}
                    />
                    {t('pacsSettings.worklistsEnabled')}
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={worklistsFilterIssuerAet}
                      onChange={e => setWorklistsFilterIssuerAet(e.target.checked)}
                    />
                    {t('pacsSettings.worklistsFilterIssuer')}
                  </label>
                  {inboundWarning ? (
                    <p className="rounded border border-amber-600/40 bg-amber-950/30 px-3 py-2 text-xs text-amber-200">
                      {t('pacsSettings.inboundWarning')}
                    </p>
                  ) : null}
                  <p className="text-muted-foreground text-xs font-medium">
                    {t('pacsSettings.dicomSecurityTitle')}
                  </p>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={restrictInbound}
                      onChange={e => setRestrictInbound(e.target.checked)}
                    />
                    {t('pacsSettings.restrictInbound')}
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={checkCalledAet}
                      onChange={e => setCheckCalledAet(e.target.checked)}
                    />
                    {t('pacsSettings.checkCalledAet')}
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={checkModalityHost}
                      onChange={e => setCheckModalityHost(e.target.checked)}
                    />
                    {t('pacsSettings.checkModalityHost')}
                  </label>
                  <p className="text-muted-foreground text-xs">{t('pacsSettings.dicomSecurityHint')}</p>

                  <div className="border-border mt-2 rounded border p-3">
                    <p className="mb-2 text-sm font-medium">{t('pacsSettings.dicomTlsTitle')}</p>
                    <p className="text-muted-foreground mb-2 text-xs">{t('pacsSettings.dicomTlsHint')}</p>
                    {dicomTlsStatus ? (
                      <>
                        <p className="text-muted-foreground text-xs">
                          {dicomTlsConfig.enabled
                            ? t('pacsSettings.dicomTlsEnabled', { port: dicomTlsStatus.dicom_port })
                            : t('pacsSettings.dicomTlsDisabled')}
                          {dicomTlsStatus.orthanc.enabled
                            ? ` · ${t('pacsSettings.dicomTlsOrthancActive')}`
                            : ` · ${t('pacsSettings.dicomTlsOrthancInactive')}`}
                        </p>
                        <p className="text-muted-foreground text-xs">
                          {dicomTlsStatus.certificates.server_present
                            ? t('pacsSettings.dicomTlsCertsOk')
                            : t('pacsSettings.dicomTlsCertsMissing')}
                        </p>
                        {dicomTlsStatus.certificates.server_certificate ? (
                          <p className="text-muted-foreground break-all text-xs">
                            {t('pacsSettings.dicomTlsCertPath', {
                              path: dicomTlsStatus.certificates.server_certificate,
                            })}
                          </p>
                        ) : null}
                        {dicomTlsStatus.stats.last_at ? (
                          <p className="text-muted-foreground text-xs">
                            {dicomTlsStatus.stats.last_success
                              ? t('pacsSettings.dicomTlsLastOk', {
                                  at: formatTs(dicomTlsStatus.stats.last_at, i18n.language),
                                  actor: dicomTlsStatus.stats.last_actor || '—',
                                })
                              : t('pacsSettings.dicomTlsLastFail', {
                                  at: formatTs(dicomTlsStatus.stats.last_at, i18n.language),
                                  error: dicomTlsStatus.stats.last_error || '—',
                                })}
                          </p>
                        ) : null}
                      </>
                    ) : null}
                    {!isAdmin ? (
                      <p className="text-muted-foreground mt-2 text-xs">{t('pacsSettings.opsAdminOnly')}</p>
                    ) : (
                      <div className="mt-2 flex flex-col gap-2">
                        <label className="flex items-center gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={dicomTlsConfig.enabled}
                            onChange={e =>
                              setDicomTlsConfig(prev => ({ ...prev, enabled: e.target.checked }))
                            }
                          />
                          {t('pacsSettings.dicomTlsEnabledToggle')}
                        </label>
                        <label className="flex items-center gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={dicomTlsConfig.remote_certificate_required}
                            onChange={e =>
                              setDicomTlsConfig(prev => ({
                                ...prev,
                                remote_certificate_required: e.target.checked,
                              }))
                            }
                          />
                          {t('pacsSettings.dicomTlsRequireClientCert')}
                        </label>
                        <p className="text-muted-foreground text-xs">{t('pacsSettings.dicomTlsLegacyNote')}</p>
                        <div className="flex flex-wrap justify-end gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={handleGenerateDicomTlsCerts}
                            disabled={dicomTlsSaving || saving}
                          >
                            {t('pacsSettings.dicomTlsGenerate')}
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={handleTestDicomTlsEcho}
                            disabled={dicomTlsTesting || saving || !dicomTlsConfig.enabled}
                          >
                            {dicomTlsTesting
                              ? t('pacsSettings.dicomTlsTesting')
                              : t('pacsSettings.dicomTlsTestEcho')}
                          </Button>
                          <Button
                            size="sm"
                            onClick={handleSaveDicomTls}
                            disabled={dicomTlsSaving || saving}
                          >
                            {t('pacsSettings.saveDicomTls')}
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>

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
              <p className="text-muted-foreground text-xs">{t('pacsSettings.equipmentSecurityHint')}</p>
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
              {worklistLoading ? (
                <p className="text-sm">{t('pacsSettings.loadingWorklist')}</p>
              ) : (
                <>
                  <div className="border-border rounded border p-3">
                    <p className="mb-2 text-sm font-medium">{t('pacsSettings.mwlDataSource')}</p>
                    <p className="text-muted-foreground mb-3 text-xs">{t('pacsSettings.mwlDataSourceHint')}</p>
                    {!isAdmin ? (
                      <p className="text-muted-foreground text-xs">{t('pacsSettings.opsAdminOnly')}</p>
                    ) : (
                      <div className="flex flex-col gap-3">
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
                            {t('pacsSettings.mwlDriver')}
                            <select
                              className="border-input bg-background rounded-md border px-3 py-2 text-sm"
                              value={mwlSql.driver}
                              onChange={e => {
                                const driver = e.target.value;
                                const meta = (mwlSql.available_drivers || []).find(d => d.id === driver);
                                setMwlSql(prev => ({
                                  ...prev,
                                  driver,
                                  port: meta?.default_port || prev.port,
                                }));
                              }}
                            >
                              {(mwlSql.available_drivers || [{ id: 'postgresql', label: 'PostgreSQL', default_port: 5432 }]).map(
                                d => (
                                  <option key={d.id} value={d.id}>
                                    {d.label}
                                  </option>
                                )
                              )}
                            </select>
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.mwlMode')}
                            <select
                              className="border-input bg-background rounded-md border px-3 py-2 text-sm"
                              value={mwlSql.mode}
                              onChange={e =>
                                setMwlSql(prev => ({
                                  ...prev,
                                  mode: e.target.value as MwlSqlForm['mode'],
                                }))
                              }
                            >
                              <option value="table">{t('pacsSettings.mwlModeTable')}</option>
                              <option value="custom">{t('pacsSettings.mwlModeCustom')}</option>
                            </select>
                          </label>
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
                              onChange={e => setMwlSql(prev => ({ ...prev, database: e.target.value }))}
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.sqlUser')}
                            <Input
                              value={mwlSql.username}
                              onChange={e => setMwlSql(prev => ({ ...prev, username: e.target.value }))}
                            />
                          </label>
                          {mwlSql.mode === 'table' ? (
                            <label className="flex flex-col gap-1 text-xs sm:col-span-2">
                              {t('pacsSettings.sqlTable')}
                              <Input
                                value={mwlSql.table}
                                onChange={e => setMwlSql(prev => ({ ...prev, table: e.target.value }))}
                              />
                            </label>
                          ) : (
                            <label className="col-span-1 flex flex-col gap-1 text-xs sm:col-span-2">
                              {t('pacsSettings.mwlCustomSql')}
                              <textarea
                                className="border-input bg-background min-h-[120px] rounded-md border px-3 py-2 font-mono text-xs"
                                value={mwlSql.custom_sql}
                                onChange={e =>
                                  setMwlSql(prev => ({ ...prev, custom_sql: e.target.value }))
                                }
                              />
                            </label>
                          )}
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.sqlPasswordEnv')}
                            <Input
                              value={mwlSql.password_env}
                              onChange={e =>
                                setMwlSql(prev => ({ ...prev, password_env: e.target.value }))
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.sqlInterval')}
                            <Input
                              type="number"
                              min={1}
                              max={1440}
                              value={mwlSql.sync_interval_minutes}
                              onChange={e =>
                                setMwlSql(prev => ({
                                  ...prev,
                                  sync_interval_minutes: Math.max(1, Number(e.target.value) || 5),
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

                        {mwlSql.mode === 'custom' ? (
                          <div className="border-border rounded border p-2">
                            <p className="mb-2 text-xs font-medium">{t('pacsSettings.mwlFieldMapping')}</p>
                            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                              {MWL_MAP_FIELDS.map(field => (
                                <label
                                  key={field}
                                  className="flex flex-col gap-1 text-xs"
                                >
                                  {t(`pacsSettings.mwlField.${field}`)}
                                  <Input
                                    value={mwlSql.field_mapping[field] || ''}
                                    onChange={e =>
                                      setMwlSql(prev => ({
                                        ...prev,
                                        field_mapping: {
                                          ...prev.field_mapping,
                                          [field]: e.target.value,
                                        },
                                      }))
                                    }
                                  />
                                </label>
                              ))}
                            </div>
                          </div>
                        ) : null}

                        <label className="flex flex-col gap-1 text-xs">
                          {t('pacsSettings.mwlModalityFilter')}
                          <Input
                            value={mwlSql.modality_filter.join(',')}
                            onChange={e =>
                              setMwlSql(prev => ({
                                ...prev,
                                modality_filter: e.target.value
                                  .split(',')
                                  .map(v => v.trim().toUpperCase())
                                  .filter(Boolean),
                              }))
                            }
                            placeholder="CT,MR,DX"
                          />
                        </label>

                        <div className="border-border rounded border p-2">
                          <p className="mb-2 text-xs font-medium">{t('pacsSettings.mwlModalityRoutes')}</p>
                          {mwlSql.modality_routes.map((route, index) => (
                            <div
                              key={index}
                              className="mb-2 grid grid-cols-1 gap-2 sm:grid-cols-3"
                            >
                              <Input
                                placeholder={t('pacsSettings.modality')}
                                value={route.modality}
                                onChange={e =>
                                  setMwlSql(prev => ({
                                    ...prev,
                                    modality_routes: prev.modality_routes.map((item, i) =>
                                      i === index
                                        ? { ...item, modality: e.target.value.toUpperCase() }
                                        : item
                                    ),
                                  }))
                                }
                              />
                              <Input
                                placeholder={t('pacsSettings.stationAet')}
                                value={route.station_aet}
                                onChange={e =>
                                  setMwlSql(prev => ({
                                    ...prev,
                                    modality_routes: prev.modality_routes.map((item, i) =>
                                      i === index
                                        ? { ...item, station_aet: e.target.value.toUpperCase() }
                                        : item
                                    ),
                                  }))
                                }
                              />
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() =>
                                  setMwlSql(prev => ({
                                    ...prev,
                                    modality_routes: prev.modality_routes.filter((_, i) => i !== index),
                                  }))
                                }
                              >
                                {t('pacsSettings.remove')}
                              </Button>
                            </div>
                          ))}
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() =>
                              setMwlSql(prev => ({
                                ...prev,
                                modality_routes: [...prev.modality_routes, { modality: '', station_aet: '' }],
                              }))
                            }
                          >
                            {t('pacsSettings.mwlAddRoute')}
                          </Button>
                        </div>

                        <div className="flex flex-wrap justify-end gap-2">
                          <Button
                            size="sm"
                            onClick={handleSaveMwlSql}
                            disabled={saving}
                          >
                            {t('pacsSettings.saveSql')}
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={handleTestMwlConnection}
                            disabled={saving}
                          >
                            {t('pacsSettings.mwlTestConnection')}
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={handlePreviewMwlSql}
                            disabled={saving}
                          >
                            {t('pacsSettings.mwlPreview')}
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={handleMwlSync}
                            disabled={saving || !mwlSql.enabled}
                          >
                            {t('pacsSettings.mwlSyncNow')}
                          </Button>
                        </div>

                        {mwlPreview.length > 0 ? (
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
                                {mwlPreview.map(entry => (
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
                        ) : null}
                      </div>
                    )}
                  </div>

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
                </>
              )}
            </TabsContent>

            <TabsContent
              value="integration"
              className="mt-3 flex w-full max-w-full flex-col gap-3 data-[state=inactive]:hidden"
            >
              {integrationLoading ? (
                <p className="text-sm">{t('pacsSettings.loadingIntegration')}</p>
              ) : mwlStatus ? (
                <>
                  <div className="border-border rounded border p-3 text-sm">
                    <p className="font-medium">{t('pacsSettings.adTitle')}</p>
                    <p className="text-muted-foreground mt-1 text-xs">{t('pacsSettings.adHint')}</p>
                    {adStatus ? (
                      <>
                        <p className="text-muted-foreground mt-2 text-xs">
                          {adConfig.enabled ? t('pacsSettings.adEnabled') : t('pacsSettings.adDisabled')}
                          {adConfig.keycloak_configured
                            ? ` · ${t('pacsSettings.adKeycloakOk', { realm: adConfig.keycloak_realm })}`
                            : ` · ${t('pacsSettings.adKeycloakMissing')}`}
                        </p>
                        {adStatus.sync.last_at ? (
                          <p className="text-muted-foreground text-xs">
                            {t('pacsSettings.adLastSync', {
                              at: formatTs(adStatus.sync.last_at, i18n.language),
                              actor: adStatus.sync.last_actor || '—',
                              users: adStatus.sync.users_imported,
                              groups: adStatus.sync.groups_mapped,
                            })}
                          </p>
                        ) : null}
                        {adStatus.sync.last_error ? (
                          <p className="text-destructive mt-1 text-xs">
                            {t('pacsSettings.adError', { error: adStatus.sync.last_error })}
                          </p>
                        ) : null}
                      </>
                    ) : null}
                  </div>

                  <div className="border-border rounded border p-3">
                    <p className="mb-2 text-sm font-medium">{t('pacsSettings.adConfigTitle')}</p>
                    {!isAdmin ? (
                      <p className="text-muted-foreground text-xs">{t('pacsSettings.opsAdminOnly')}</p>
                    ) : (
                      <div className="flex flex-col gap-2">
                        <label className="flex items-center gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={adConfig.enabled}
                            onChange={e => setAdConfig(prev => ({ ...prev, enabled: e.target.checked }))}
                          />
                          {t('pacsSettings.adEnabledToggle')}
                        </label>
                        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                          <label className="flex flex-col gap-1 text-xs sm:col-span-2">
                            {t('pacsSettings.adConnectionUrl')}
                            <Input
                              value={adConfig.connection_url}
                              onChange={e =>
                                setAdConfig(prev => ({ ...prev, connection_url: e.target.value }))
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs sm:col-span-2">
                            {t('pacsSettings.adBindDn')}
                            <Input
                              value={adConfig.bind_dn}
                              onChange={e => setAdConfig(prev => ({ ...prev, bind_dn: e.target.value }))}
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.adPasswordEnv')}
                            <Input
                              value={adConfig.bind_password_env}
                              onChange={e =>
                                setAdConfig(prev => ({ ...prev, bind_password_env: e.target.value }))
                              }
                            />
                          </label>
                          <label className="flex items-center gap-2 text-sm self-end pb-2">
                            <input
                              type="checkbox"
                              checked={adConfig.use_ssl}
                              onChange={e => setAdConfig(prev => ({ ...prev, use_ssl: e.target.checked }))}
                            />
                            {t('pacsSettings.adUseSsl')}
                          </label>
                          <label className="flex flex-col gap-1 text-xs sm:col-span-2">
                            {t('pacsSettings.adUsersDn')}
                            <Input
                              value={adConfig.users_dn}
                              onChange={e => setAdConfig(prev => ({ ...prev, users_dn: e.target.value }))}
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs sm:col-span-2">
                            {t('pacsSettings.adGroupsDn')}
                            <Input
                              value={adConfig.groups_dn}
                              onChange={e => setAdConfig(prev => ({ ...prev, groups_dn: e.target.value }))}
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.adUsernameAttr')}
                            <Input
                              value={adConfig.username_ldap_attribute}
                              onChange={e =>
                                setAdConfig(prev => ({
                                  ...prev,
                                  username_ldap_attribute: e.target.value,
                                }))
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.adFullSyncHours')}
                            <Input
                              type="number"
                              value={adConfig.full_sync_period_hours}
                              onChange={e =>
                                setAdConfig(prev => ({
                                  ...prev,
                                  full_sync_period_hours: Number(e.target.value) || 24,
                                }))
                              }
                            />
                          </label>
                        </div>
                        <label className="flex items-center gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={adConfig.import_users}
                            onChange={e =>
                              setAdConfig(prev => ({ ...prev, import_users: e.target.checked }))
                            }
                          />
                          {t('pacsSettings.adImportUsers')}
                        </label>
                        {!adConfig.bind_password_configured ? (
                          <p className="text-amber-600 text-xs">{t('pacsSettings.adPasswordMissing')}</p>
                        ) : null}
                        <p className="text-muted-foreground text-xs font-medium">
                          {t('pacsSettings.adGroupMappings')}
                        </p>
                        {adConfig.group_mappings.map((mapping, index) => (
                          <div
                            key={`ad-map-${index}`}
                            className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_1fr_auto]"
                          >
                            <Input
                              placeholder={t('pacsSettings.adGroupCn')}
                              value={mapping.ad_group_cn}
                              onChange={e => {
                                const next = [...adConfig.group_mappings];
                                next[index] = { ...next[index], ad_group_cn: e.target.value };
                                setAdConfig(prev => ({ ...prev, group_mappings: next }));
                              }}
                            />
                            <select
                              className="border-input bg-background h-9 rounded-md border px-3 text-sm"
                              value={mapping.lex_group}
                              onChange={e => {
                                const next = [...adConfig.group_mappings];
                                next[index] = { ...next[index], lex_group: e.target.value };
                                setAdConfig(prev => ({ ...prev, group_mappings: next }));
                              }}
                            >
                              {(adStatus?.lex_groups || ['radiologista', 'tecnico', 'admin']).map(group => (
                                <option
                                  key={group}
                                  value={group}
                                >
                                  {group}
                                </option>
                              ))}
                            </select>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => {
                                const next = adConfig.group_mappings.filter((_, i) => i !== index);
                                setAdConfig(prev => ({
                                  ...prev,
                                  group_mappings: next.length
                                    ? next
                                    : [{ ad_group_cn: '', lex_group: 'radiologista' }],
                                }));
                              }}
                            >
                              {t('pacsSettings.adRemoveMapping')}
                            </Button>
                          </div>
                        ))}
                        <div className="flex justify-start">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() =>
                              setAdConfig(prev => ({
                                ...prev,
                                group_mappings: [
                                  ...prev.group_mappings,
                                  { ad_group_cn: '', lex_group: 'tecnico' },
                                ],
                              }))
                            }
                          >
                            {t('pacsSettings.adAddMapping')}
                          </Button>
                        </div>
                        <div className="flex flex-wrap justify-end gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={handleAdTest}
                            disabled={saving || !adConfig.enabled}
                          >
                            {t('pacsSettings.adTest')}
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={handleAdSync}
                            disabled={saving || !adConfig.enabled}
                          >
                            {t('pacsSettings.adSyncNow')}
                          </Button>
                          <Button
                            size="sm"
                            onClick={handleSaveAd}
                            disabled={saving}
                          >
                            {t('pacsSettings.saveAd')}
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="border-border rounded border p-3 text-sm">
                    <p className="font-medium">{t('pacsSettings.mppsTitle')}</p>
                    <p className="text-muted-foreground mt-1 text-xs">{t('pacsSettings.mppsHint')}</p>
                    {mppsStatus ? (
                      <>
                        <p className="text-muted-foreground mt-2 text-xs">
                          {mppsConfig.enabled
                            ? t('pacsSettings.mppsEnabled', {
                                aet: mppsConfig.aet,
                                port: mppsConfig.listen_port,
                              })
                            : t('pacsSettings.mppsDisabled')}
                          {mppsStatus.server_running
                            ? ` · ${t('pacsSettings.mppsRunning')}`
                            : ` · ${t('pacsSettings.mppsStopped')}`}
                        </p>
                        <p className="text-muted-foreground text-xs">
                          {t('pacsSettings.mppsStats', {
                            messages: mppsStatus.stats.messages_total,
                            completed: mppsStatus.stats.completed_total,
                            removed: mppsStatus.stats.mwl_removed_total,
                          })}
                        </p>
                        {mppsStatus.stats.last_at ? (
                          <p className="text-muted-foreground text-xs">
                            {t('pacsSettings.mppsLast', {
                              at: formatTs(mppsStatus.stats.last_at, i18n.language),
                              accession: mppsStatus.stats.last_accession || '—',
                              status: mppsStatus.stats.last_status || '—',
                            })}
                          </p>
                        ) : null}
                      </>
                    ) : null}
                  </div>

                  <div className="border-border rounded border p-3">
                    <p className="mb-2 text-sm font-medium">{t('pacsSettings.mppsConfigTitle')}</p>
                    {!isAdmin ? (
                      <p className="text-muted-foreground text-xs">{t('pacsSettings.opsAdminOnly')}</p>
                    ) : (
                      <div className="flex flex-col gap-2">
                        <label className="flex items-center gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={mppsConfig.enabled}
                            onChange={e => setMppsConfig(prev => ({ ...prev, enabled: e.target.checked }))}
                          />
                          {t('pacsSettings.mppsEnabledToggle')}
                        </label>
                        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.mppsAet')}
                            <Input
                              value={mppsConfig.aet}
                              onChange={e =>
                                setMppsConfig(prev => ({ ...prev, aet: e.target.value.toUpperCase() }))
                              }
                              maxLength={16}
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.mppsListenPort')}
                            <Input
                              type="number"
                              value={mppsConfig.listen_port}
                              onChange={e =>
                                setMppsConfig(prev => ({
                                  ...prev,
                                  listen_port: Number(e.target.value) || 4243,
                                }))
                              }
                            />
                          </label>
                        </div>
                        <label className="flex items-center gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={mppsConfig.auto_complete_mwl}
                            onChange={e =>
                              setMppsConfig(prev => ({ ...prev, auto_complete_mwl: e.target.checked }))
                            }
                          />
                          {t('pacsSettings.mppsAutoComplete')}
                        </label>
                        <label className="flex items-center gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={mppsConfig.complete_on_discontinued}
                            onChange={e =>
                              setMppsConfig(prev => ({
                                ...prev,
                                complete_on_discontinued: e.target.checked,
                              }))
                            }
                          />
                          {t('pacsSettings.mppsCompleteDiscontinued')}
                        </label>
                        <div className="flex justify-end">
                          <Button
                            size="sm"
                            onClick={handleSaveMpps}
                            disabled={saving}
                          >
                            {t('pacsSettings.saveMpps')}
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="border-border rounded border p-3 text-sm">
                    <p className="font-medium">{t('pacsSettings.qrTitle')}</p>
                    <p className="text-muted-foreground mt-1 text-xs">{t('pacsSettings.qrHint')}</p>
                    {qrStatus ? (
                      <>
                        <p className="text-muted-foreground mt-2 text-xs">
                          {t('pacsSettings.qrScp', {
                            aet: qrStatus.dicom_aet,
                            port: qrStatus.dicom_port,
                            size: qrStatus.orthanc.query_retrieve_size,
                          })}
                        </p>
                        <p className="text-muted-foreground text-xs">
                          {qrStatus.orthanc.dicom_always_allow_find ||
                          qrStatus.orthanc.dicom_always_allow_move ||
                          qrStatus.orthanc.dicom_always_allow_get
                            ? t('pacsSettings.qrPolicyOpen')
                            : t('pacsSettings.qrPolicyRestricted')}
                        </p>
                        <p className="text-muted-foreground text-xs">
                          {t('pacsSettings.qrConsumers', { count: qrStatus.consumer_count })}
                        </p>
                        {qrStatus.stats.last_at ? (
                          <p className="text-muted-foreground text-xs">
                            {qrStatus.stats.last_success
                              ? t('pacsSettings.qrLastOk', {
                                  at: formatTs(qrStatus.stats.last_at, i18n.language),
                                  count: qrStatus.stats.last_find_count,
                                  actor: qrStatus.stats.last_actor || '—',
                                })
                              : t('pacsSettings.qrLastFail', {
                                  at: formatTs(qrStatus.stats.last_at, i18n.language),
                                  error: qrStatus.stats.last_error || '—',
                                })}
                          </p>
                        ) : null}
                        {isAdmin ? (
                          <div className="mt-2 flex justify-end">
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={handleQrTestFind}
                              disabled={qrTesting || saving}
                            >
                              {qrTesting ? t('pacsSettings.qrTesting') : t('pacsSettings.qrTestFind')}
                            </Button>
                          </div>
                        ) : null}
                      </>
                    ) : null}
                  </div>

                  <div className="border-border rounded border p-3 text-sm">
                    <p className="font-medium">{t('pacsSettings.hl7Title')}</p>
                    {hl7Status ? (
                      <>
                        <p className="text-muted-foreground mt-1 text-xs">
                          {hl7Status.config.enabled
                            ? t('pacsSettings.hl7Enabled', { port: hl7Status.config.listen_port })
                            : t('pacsSettings.hl7Disabled')}
                        </p>
                        <p className="text-muted-foreground text-xs">
                          {t('pacsSettings.hl7Messages', { count: hl7Status.stats.messages_total })}
                        </p>
                        {hl7Status.stats.last_at ? (
                          <p className="text-muted-foreground text-xs">
                            {t('pacsSettings.hl7Last', {
                              at: formatTs(hl7Status.stats.last_at, i18n.language),
                              accession: hl7Status.stats.last_accession || '—',
                              control: hl7Status.stats.last_control || '—',
                            })}
                          </p>
                        ) : null}
                        {hl7Status.stats.last_error ? (
                          <p className="text-destructive mt-1 text-xs">
                            {t('pacsSettings.hl7Error', { error: hl7Status.stats.last_error })}
                          </p>
                        ) : null}
                      </>
                    ) : null}
                  </div>

                  <div className="border-border rounded border p-3">
                    <p className="mb-2 text-sm font-medium">{t('pacsSettings.hl7ConfigTitle')}</p>
                    {!isAdmin ? (
                      <p className="text-muted-foreground text-xs">{t('pacsSettings.opsAdminOnly')}</p>
                    ) : (
                      <div className="flex flex-col gap-2">
                        <label className="flex items-center gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={hl7Config.enabled}
                            onChange={e => setHl7Config(prev => ({ ...prev, enabled: e.target.checked }))}
                          />
                          {t('pacsSettings.hl7EnabledToggle')}
                        </label>
                        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.hl7ListenHost')}
                            <Input
                              value={hl7Config.listen_host}
                              onChange={e =>
                                setHl7Config(prev => ({ ...prev, listen_host: e.target.value }))
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.hl7ListenPort')}
                            <Input
                              type="number"
                              value={hl7Config.listen_port}
                              onChange={e =>
                                setHl7Config(prev => ({
                                  ...prev,
                                  listen_port: Number(e.target.value) || 2575,
                                }))
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.hl7DefaultStation')}
                            <Input
                              value={hl7Config.default_station_aet}
                              onChange={e =>
                                setHl7Config(prev => ({
                                  ...prev,
                                  default_station_aet: e.target.value.toUpperCase(),
                                }))
                              }
                              maxLength={16}
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.hl7SendingApp')}
                            <Input
                              value={hl7Config.sending_application}
                              onChange={e =>
                                setHl7Config(prev => ({
                                  ...prev,
                                  sending_application: e.target.value,
                                }))
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs sm:col-span-2">
                            {t('pacsSettings.hl7SendingFacility')}
                            <Input
                              value={hl7Config.sending_facility}
                              onChange={e =>
                                setHl7Config(prev => ({ ...prev, sending_facility: e.target.value }))
                              }
                            />
                          </label>
                        </div>
                        <label className="flex items-center gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={hl7Config.auto_sync}
                            onChange={e =>
                              setHl7Config(prev => ({ ...prev, auto_sync: e.target.checked }))
                            }
                          />
                          {t('pacsSettings.hl7AutoSync')}
                        </label>
                        <label className="flex items-center gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={hl7Config.map_modality_to_station}
                            onChange={e =>
                              setHl7Config(prev => ({
                                ...prev,
                                map_modality_to_station: e.target.checked,
                              }))
                            }
                          />
                          {t('pacsSettings.hl7MapModality')}
                        </label>
                        <div className="flex justify-end">
                          <Button
                            size="sm"
                            onClick={handleSaveHl7}
                            disabled={saving}
                          >
                            {t('pacsSettings.saveHl7')}
                          </Button>
                        </div>
                        <label className="mt-2 flex flex-col gap-1 text-xs">
                          {t('pacsSettings.hl7TestMessage')}
                          <textarea
                            className="border-input bg-background min-h-[80px] rounded-md border px-3 py-2 text-sm"
                            value={hl7TestMessage}
                            onChange={e => setHl7TestMessage(e.target.value)}
                          />
                        </label>
                        <label className="flex items-center gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={hl7TestApply}
                            onChange={e => setHl7TestApply(e.target.checked)}
                          />
                          {t('pacsSettings.hl7TestApply')}
                        </label>
                        <div className="flex justify-end">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={handleHl7Test}
                            disabled={saving || !hl7TestMessage.trim()}
                          >
                            {t('pacsSettings.hl7TestRun')}
                          </Button>
                        </div>
                      </div>
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
                        onClick={() => void loadIntegrationData()}
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
                </>
              ) : (
                <Button
                  variant="outline"
                  onClick={() => void loadIntegrationData()}
                >
                  {t('pacsSettings.loadAdmin')}
                </Button>
              )}
            </TabsContent>

            <TabsContent
              value="migration"
              className="mt-3 flex w-full max-w-full flex-col gap-3 data-[state=inactive]:hidden"
            >
              {migrationLoading && !migrationStatus ? (
                <p className="text-sm">{t('pacsSettings.loadingMigration')}</p>
              ) : (
                <>
                  <p className="text-muted-foreground text-xs">{t('pacsSettings.migrationHint')}</p>

                  {migrationStatus ? (
                    <div className="border-border rounded border p-3 text-sm">
                      <p className="font-medium">{t('pacsSettings.migrationStatus')}</p>
                      <p className="text-muted-foreground mt-1 text-xs">
                        {migrationStatusLabel(migrationStatus.status, t)}
                      </p>
                      <p className="text-muted-foreground text-xs">
                        {t('pacsSettings.migrationProgress', {
                          percent: migrationStatus.progress_percent,
                          cursor: migrationStatus.cursor,
                          total: migrationStatus.queue_total,
                        })}
                      </p>
                      <p className="text-muted-foreground text-xs">
                        {t('pacsSettings.migrationPending', { count: migrationStatus.pending })}
                      </p>
                      <p className="text-muted-foreground text-xs">
                        {t('pacsSettings.migrationStats', {
                          completed: migrationStatus.stats.completed,
                          skipped: migrationStatus.stats.skipped,
                          failed: migrationStatus.stats.failed,
                          instances: migrationStatus.stats.instances_imported,
                        })}
                      </p>
                      {migrationStatus.last_error ? (
                        <p className="text-destructive mt-1 text-xs">
                          {t('pacsSettings.migrationLastError', { error: migrationStatus.last_error })}
                        </p>
                      ) : null}
                    </div>
                  ) : null}

                  <div className="border-border rounded border p-3">
                    <p className="mb-2 text-sm font-medium">{t('pacsSettings.migrationTitle')}</p>
                    {!isAdmin ? (
                      <p className="text-muted-foreground text-xs">{t('pacsSettings.opsAdminOnly')}</p>
                    ) : (
                      <div className="flex flex-col gap-3">
                        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.migrationSourceLabel')}
                            <Input
                              value={migrationForm.source.label}
                              onChange={e =>
                                setMigrationForm(prev => ({
                                  ...prev,
                                  source: { ...prev.source, label: e.target.value },
                                }))
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.migrationSourceAet')}
                            <Input
                              value={migrationForm.source.aet}
                              onChange={e =>
                                setMigrationForm(prev => ({
                                  ...prev,
                                  source: { ...prev.source, aet: e.target.value.toUpperCase() },
                                }))
                              }
                              maxLength={16}
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.migrationSourceHost')}
                            <Input
                              value={migrationForm.source.host}
                              onChange={e =>
                                setMigrationForm(prev => ({
                                  ...prev,
                                  source: { ...prev.source, host: e.target.value },
                                }))
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.migrationSourcePort')}
                            <Input
                              type="number"
                              value={migrationForm.source.port}
                              onChange={e =>
                                setMigrationForm(prev => ({
                                  ...prev,
                                  source: {
                                    ...prev.source,
                                    port: Number(e.target.value) || 104,
                                  },
                                }))
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.migrationFilterFrom')}
                            <Input
                              value={migrationForm.filters.study_date_from}
                              onChange={e =>
                                setMigrationForm(prev => ({
                                  ...prev,
                                  filters: { ...prev.filters, study_date_from: e.target.value },
                                }))
                              }
                              placeholder="20200101"
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.migrationFilterTo')}
                            <Input
                              value={migrationForm.filters.study_date_to}
                              onChange={e =>
                                setMigrationForm(prev => ({
                                  ...prev,
                                  filters: { ...prev.filters, study_date_to: e.target.value },
                                }))
                              }
                              placeholder="20251231"
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.migrationFilterPatient')}
                            <Input
                              value={migrationForm.filters.patient_id}
                              onChange={e =>
                                setMigrationForm(prev => ({
                                  ...prev,
                                  filters: { ...prev.filters, patient_id: e.target.value },
                                }))
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.migrationFilterModality')}
                            <Input
                              value={migrationForm.filters.modality}
                              onChange={e =>
                                setMigrationForm(prev => ({
                                  ...prev,
                                  filters: {
                                    ...prev.filters,
                                    modality: e.target.value.toUpperCase(),
                                  },
                                }))
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.migrationBatchSize')}
                            <Input
                              type="number"
                              min={1}
                              max={10}
                              value={migrationForm.batch_size}
                              onChange={e =>
                                setMigrationForm(prev => ({
                                  ...prev,
                                  batch_size: Math.max(1, Number(e.target.value) || 1),
                                }))
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.migrationPauseSeconds')}
                            <Input
                              type="number"
                              min={0}
                              max={300}
                              value={migrationForm.pause_seconds}
                              onChange={e =>
                                setMigrationForm(prev => ({
                                  ...prev,
                                  pause_seconds: Math.max(0, Number(e.target.value) || 0),
                                }))
                              }
                            />
                          </label>
                        </div>
                        <label className="flex items-center gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={migrationForm.skip_existing}
                            onChange={e =>
                              setMigrationForm(prev => ({
                                ...prev,
                                skip_existing: e.target.checked,
                              }))
                            }
                          />
                          {t('pacsSettings.migrationSkipExisting')}
                        </label>
                        <div className="flex flex-wrap justify-end gap-2">
                          <Button
                            size="sm"
                            onClick={handleSaveMigration}
                            disabled={saving}
                          >
                            {t('pacsSettings.migrationSave')}
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() =>
                              void handleMigrationAction(
                                'test-echo',
                                t('pacsSettings.messages.migrationEchoOk'),
                                'pacsSettings.errors.migrationEcho'
                              )
                            }
                            disabled={saving}
                          >
                            {t('pacsSettings.migrationTestEcho')}
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() =>
                              void handleMigrationAction(
                                'discover',
                                '',
                                'pacsSettings.errors.migrationDiscover'
                              )
                            }
                            disabled={saving}
                          >
                            {t('pacsSettings.migrationDiscover')}
                          </Button>
                          <Button
                            size="sm"
                            onClick={() =>
                              void handleMigrationAction(
                                'start',
                                t('pacsSettings.messages.migrationStarted'),
                                'pacsSettings.errors.migrationStart'
                              )
                            }
                            disabled={saving}
                          >
                            {t('pacsSettings.migrationStart')}
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() =>
                              void handleMigrationAction(
                                'pause',
                                t('pacsSettings.messages.migrationPaused'),
                                'pacsSettings.errors.migrationPause'
                              )
                            }
                            disabled={saving}
                          >
                            {t('pacsSettings.migrationPause')}
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() =>
                              void handleMigrationAction(
                                'reset',
                                t('pacsSettings.messages.migrationReset'),
                                'pacsSettings.errors.migrationReset'
                              )
                            }
                            disabled={saving}
                          >
                            {t('pacsSettings.migrationReset')}
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                </>
              )}
            </TabsContent>

            <TabsContent
              value="storage"
              className="mt-3 flex w-full max-w-full flex-col gap-3 data-[state=inactive]:hidden"
            >
              {storageLoading && !storageStatus ? (
                <p className="text-sm">{t('pacsSettings.loadingStorage')}</p>
              ) : (
                <>
                  <p className="text-muted-foreground text-xs">{t('pacsSettings.storageHint')}</p>

                  {pacsStats ? (
                    <div className="border-border rounded-lg border p-3">
                      <PacsStatsPanel stats={pacsStats} />
                    </div>
                  ) : null}

                  <div className="border-border rounded border p-3 text-sm">
                    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                      <p className="font-medium">{t('pacsSettings.backup')}</p>
                      {isAdmin ? (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => void handleBackupTrigger()}
                          disabled={saving}
                        >
                          {t('pacsSettings.backupRunNow')}
                        </Button>
                      ) : null}
                    </div>
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
                              : t('pacsSettings.backupPending')}
                        </p>
                      </>
                    ) : (
                      <p className="text-muted-foreground mt-1 text-xs">
                        {t('pacsSettings.loadingBackupStatus')}
                      </p>
                    )}
                  </div>

                  {storageStatus ? (
                    <div className="border-border rounded border p-3 text-sm">
                      <p className="font-medium">{t('pacsSettings.storageStatus')}</p>
                      <p className="text-muted-foreground mt-1 text-xs">
                        {storageStatusLabel(storageStatus.status, t)}
                      </p>
                      <p className="text-muted-foreground text-xs">
                        {t('pacsSettings.storageProgress', {
                          percent: storageStatus.progress_percent,
                          cursor: storageStatus.cursor,
                          total: storageStatus.queue_total,
                        })}
                      </p>
                      <p className="text-muted-foreground text-xs">
                        {t('pacsSettings.storageStats', {
                          compressed: storageStatus.stats.compressed,
                          skipped: storageStatus.stats.skipped,
                          failed: storageStatus.stats.failed,
                          instances: storageStatus.stats.instances,
                        })}
                      </p>
                      {storageStatus.last_error ? (
                        <p className="text-destructive text-xs">
                          {t('pacsSettings.storageLastError', { error: storageStatus.last_error })}
                        </p>
                      ) : null}
                    </div>
                  ) : null}

                  <div className="border-border rounded border p-3">
                    <p className="mb-2 text-sm font-medium">{t('pacsSettings.storageTitle')}</p>
                    {!isAdmin ? (
                      <p className="text-muted-foreground text-xs">{t('pacsSettings.opsAdminOnly')}</p>
                    ) : (
                      <div className="flex flex-col gap-3">
                        <label className="flex items-center gap-2 text-xs">
                          <input
                            type="checkbox"
                            checked={storageForm.enabled}
                            onChange={e =>
                              setStorageForm(prev => ({ ...prev, enabled: e.target.checked }))
                            }
                          />
                          {t('pacsSettings.storageAutoRun')}
                        </label>
                        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.storageIntervalHours')}
                            <Input
                              type="number"
                              min={1}
                              max={168}
                              value={storageForm.run_interval_hours}
                              onChange={e =>
                                setStorageForm(prev => ({
                                  ...prev,
                                  run_interval_hours: Math.max(1, Number(e.target.value) || 24),
                                }))
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.storageBatchSize')}
                            <Input
                              type="number"
                              min={1}
                              max={50}
                              value={storageForm.batch_size}
                              onChange={e =>
                                setStorageForm(prev => ({
                                  ...prev,
                                  batch_size: Math.max(1, Number(e.target.value) || 5),
                                }))
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.storagePauseSeconds')}
                            <Input
                              type="number"
                              min={0}
                              max={300}
                              value={storageForm.pause_seconds}
                              onChange={e =>
                                setStorageForm(prev => ({
                                  ...prev,
                                  pause_seconds: Math.max(0, Number(e.target.value) || 2),
                                }))
                              }
                            />
                          </label>
                        </div>

                        <p className="text-muted-foreground text-xs font-medium">
                          {t('pacsSettings.backupPolicy')}
                        </p>
                        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.backupIntervalHours')}
                            <Input
                              type="number"
                              min={1}
                              max={168}
                              value={portalOps.backup_interval_hours}
                              onChange={e =>
                                setPortalOps(prev => ({
                                  ...prev,
                                  backup_interval_hours: Math.max(1, Number(e.target.value) || 24),
                                }))
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.backupRetentionDaily')}
                            <Input
                              type="number"
                              min={1}
                              value={portalOps.backup_retention_daily}
                              onChange={e =>
                                setPortalOps(prev => ({
                                  ...prev,
                                  backup_retention_daily: Math.max(1, Number(e.target.value) || 7),
                                }))
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.backupRetentionWeekly')}
                            <Input
                              type="number"
                              min={1}
                              value={portalOps.backup_retention_weekly}
                              onChange={e =>
                                setPortalOps(prev => ({
                                  ...prev,
                                  backup_retention_weekly: Math.max(1, Number(e.target.value) || 4),
                                }))
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.backupRetentionDays')}
                            <Input
                              type="number"
                              min={1}
                              value={portalOps.backup_retention_days}
                              onChange={e =>
                                setPortalOps(prev => ({
                                  ...prev,
                                  backup_retention_days: Math.max(1, Number(e.target.value) || 14),
                                }))
                              }
                            />
                          </label>
                        </div>

                        <p className="text-muted-foreground text-xs font-medium">
                          {t('pacsSettings.storageRules')}
                        </p>
                        {storageForm.rules.length === 0 ? (
                          <p className="text-muted-foreground text-xs">{t('pacsSettings.storageNoRules')}</p>
                        ) : (
                          storageForm.rules.map((rule, index) => (
                            <div
                              key={rule.id || index}
                              className="border-border/60 grid grid-cols-1 gap-2 rounded border p-2 sm:grid-cols-2"
                            >
                              <label className="flex items-center gap-2 text-xs sm:col-span-2">
                                <input
                                  type="checkbox"
                                  checked={rule.enabled}
                                  onChange={e =>
                                    updateStorageRule(index, { enabled: e.target.checked })
                                  }
                                />
                                {t('pacsSettings.storageRuleEnabled')}
                              </label>
                              <label className="flex flex-col gap-1 text-xs">
                                {t('pacsSettings.storageMinAgeYears')}
                                <Input
                                  type="number"
                                  min={1}
                                  max={50}
                                  value={rule.min_age_years}
                                  onChange={e =>
                                    updateStorageRule(index, {
                                      min_age_years: Math.max(1, Number(e.target.value) || 1),
                                    })
                                  }
                                />
                              </label>
                              <label className="flex flex-col gap-1 text-xs">
                                {t('pacsSettings.storageTransferSyntax')}
                                <select
                                  className="border-input bg-background rounded-md border px-3 py-2 text-sm"
                                  value={rule.transfer_syntax}
                                  onChange={e =>
                                    updateStorageRule(index, { transfer_syntax: e.target.value })
                                  }
                                >
                                  {(storageStatus?.transfer_syntax_options || []).map(opt => (
                                    <option
                                      key={opt.uid}
                                      value={opt.uid}
                                    >
                                      {opt.label}
                                    </option>
                                  ))}
                                </select>
                              </label>
                              <label className="flex flex-col gap-1 text-xs sm:col-span-2">
                                {t('pacsSettings.storageModalities')}
                                <Input
                                  value={rule.modalities.join(',')}
                                  placeholder={t('pacsSettings.placeholders.viewModalities')}
                                  onChange={e =>
                                    updateStorageRule(index, {
                                      modalities: e.target.value
                                        .split(',')
                                        .map(v => v.trim().toUpperCase())
                                        .filter(Boolean),
                                    })
                                  }
                                />
                              </label>
                              <div className="flex justify-end sm:col-span-2">
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => removeStorageRule(index)}
                                >
                                  {t('pacsSettings.remove')}
                                </Button>
                              </div>
                            </div>
                          ))
                        )}
                        <div className="flex flex-wrap justify-between gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={addStorageRule}
                          >
                            {t('pacsSettings.storageAddRule')}
                          </Button>
                          <div className="flex flex-wrap gap-2">
                            <Button
                              size="sm"
                              onClick={() => void handleSaveStorage()}
                              disabled={saving}
                            >
                              {t('pacsSettings.storageSave')}
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() =>
                                void handleStorageAction(
                                  'start',
                                  t('pacsSettings.messages.storageStarted'),
                                  'pacsSettings.errors.storageStart'
                                )
                              }
                              disabled={saving}
                            >
                              {t('pacsSettings.storageRunNow')}
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() =>
                                void handleStorageAction(
                                  'pause',
                                  t('pacsSettings.messages.storagePaused'),
                                  'pacsSettings.errors.storagePause'
                                )
                              }
                              disabled={saving}
                            >
                              {t('pacsSettings.storagePause')}
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() =>
                                void handleStorageAction(
                                  'reset',
                                  t('pacsSettings.messages.storageReset'),
                                  'pacsSettings.errors.storageReset'
                                )
                              }
                              disabled={saving}
                            >
                              {t('pacsSettings.storageReset')}
                            </Button>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </>
              )}
            </TabsContent>

            <TabsContent
              value="ops"
              className="mt-3 flex w-full max-w-full flex-col gap-3 data-[state=inactive]:hidden"
            >
              {opsLoading ? (
                <p className="text-sm">{t('pacsSettings.loadingOps')}</p>
              ) : (
                <>
                  <div className="border-border rounded border p-3">
                    <p className="mb-2 text-sm font-medium">{t('pacsSettings.opsTitle')}</p>
                    {!isAdmin ? (
                      <p className="text-muted-foreground text-xs">{t('pacsSettings.opsAdminOnly')}</p>
                    ) : (
                      <div className="flex flex-col gap-3">
                        <p className="text-muted-foreground text-xs font-medium">
                          {t('pacsSettings.rateLimitTitle')}
                        </p>
                        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.rateLimitAttempts')}
                            <Input
                              type="number"
                              min={1}
                              value={portalOps.login_rate_limit_attempts}
                              onChange={e =>
                                setPortalOps(prev => ({
                                  ...prev,
                                  login_rate_limit_attempts: Math.max(
                                    1,
                                    Number(e.target.value) || 20
                                  ),
                                }))
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            {t('pacsSettings.rateLimitWindow')}
                            <Input
                              type="number"
                              min={1}
                              value={portalOps.login_rate_limit_window_seconds}
                              onChange={e =>
                                setPortalOps(prev => ({
                                  ...prev,
                                  login_rate_limit_window_seconds: Math.max(
                                    1,
                                    Number(e.target.value) || 60
                                  ),
                                }))
                              }
                            />
                          </label>
                        </div>
                        <div className="flex justify-end">
                          <Button
                            size="sm"
                            onClick={handleSavePortalOps}
                            disabled={saving}
                          >
                            {t('pacsSettings.saveOps')}
                          </Button>
                        </div>
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
              )}
            </TabsContent>
          </div>
        </Tabs>
      )}

      {error ? <p className="text-destructive shrink-0 text-sm">{error}</p> : null}
      {message ? <p className="text-primary shrink-0 text-sm">{message}</p> : null}

      <div className="flex shrink-0 justify-end gap-2 border-t pt-2">
        {isExpanded && !isPage ? (
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
            if (isPage) {
              window.close();
              return;
            }
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

  if (isPage) {
    return (
      <div className="text-foreground flex min-h-0 flex-1 flex-col gap-2 overflow-hidden">
        {panelBody}
      </div>
    );
  }

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
