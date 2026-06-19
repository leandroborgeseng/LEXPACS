import React from 'react';
import { useTranslation } from 'react-i18next';

export type ChartItem = {
  label: string;
  value: number;
  color?: string;
};

const CHART_COLORS = [
  'hsl(var(--primary))',
  '#3b82f6',
  '#22c55e',
  '#eab308',
  '#a855f7',
  '#f97316',
  '#06b6d4',
  '#ef4444',
];

export function chartColor(index: number): string {
  return CHART_COLORS[index % CHART_COLORS.length];
}

type HorizontalBarChartProps = {
  items: ChartItem[];
  emptyLabel?: string;
};

export function HorizontalBarChart({ items, emptyLabel }: HorizontalBarChartProps) {
  const { t, i18n } = useTranslation('LexPacs');
  const empty = emptyLabel ?? t('stats.noData');

  if (items.length === 0) {
    return <p className="text-muted-foreground text-xs">{empty}</p>;
  }

  const max = Math.max(...items.map(item => item.value), 1);

  return (
    <div className="flex flex-col gap-2.5">
      {items.map((item, index) => {
        const width = Math.max(2, (item.value / max) * 100);
        const color = item.color || chartColor(index);
        return (
          <div
            key={item.label}
            className="grid min-w-0 grid-cols-[minmax(64px,26%)_minmax(0,1fr)_44px] items-center gap-2 text-xs"
          >
            <span
              className="text-muted-foreground truncate"
              title={item.label}
            >
              {item.label}
            </span>
            <div className="bg-muted/50 h-3 overflow-hidden rounded-full">
              <div
                className="h-full rounded-full transition-all duration-300"
                style={{ width: `${width}%`, backgroundColor: color }}
              />
            </div>
            <span className="text-right tabular-nums">{item.value.toLocaleString(i18n.language)}</span>
          </div>
        );
      })}
    </div>
  );
}

type DonutSegment = {
  label: string;
  value: number;
  color?: string;
};

type DonutChartProps = {
  segments: DonutSegment[];
  centerLabel: string;
  centerValue: string;
};

export function DonutChart({ segments, centerLabel, centerValue }: DonutChartProps) {
  const total = segments.reduce((sum, item) => sum + item.value, 0);
  if (total <= 0) {
    return null;
  }

  let cumulative = 0;
  const gradientStops = segments
    .map(segment => {
      const start = (cumulative / total) * 100;
      cumulative += segment.value;
      const end = (cumulative / total) * 100;
      const color = segment.color || chartColor(0);
      return `${color} ${start}% ${end}%`;
    })
    .join(', ');

  return (
    <div className="flex flex-col items-center gap-3 sm:flex-row sm:items-center sm:gap-6">
      <div
        className="relative h-28 w-28 shrink-0 rounded-full"
        style={{ background: `conic-gradient(${gradientStops})` }}
      >
        <div className="bg-background absolute inset-[18%] flex flex-col items-center justify-center rounded-full text-center">
          <span className="text-muted-foreground text-[10px]">{centerLabel}</span>
          <span className="text-xs font-semibold tabular-nums">{centerValue}</span>
        </div>
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        {segments.map((segment, index) => (
          <div
            key={segment.label}
            className="flex items-center gap-2 text-xs"
          >
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ backgroundColor: segment.color || chartColor(index) }}
            />
            <span className="text-muted-foreground truncate">{segment.label}</span>
            <span className="ml-auto tabular-nums">{segment.value.toLocaleString()}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

type StatCardProps = {
  label: string;
  value: number | string;
  hint?: string;
};

export function StatCard({ label, value, hint }: StatCardProps) {
  return (
    <div className="bg-muted/40 rounded-lg border border-transparent p-3 text-center">
      <p className="text-xl font-semibold tabular-nums sm:text-2xl">{value}</p>
      <p className="text-muted-foreground mt-1 text-xs">{label}</p>
      {hint ? <p className="text-muted-foreground mt-0.5 text-[10px]">{hint}</p> : null}
    </div>
  );
}

type PacsStatsPanelProps = {
  stats: {
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
  compact?: boolean;
};

export function PacsStatsPanel({ stats, compact = false }: PacsStatsPanelProps) {
  const { t, i18n } = useTranslation('LexPacs');

  const formatCount = (value: number) => value.toLocaleString(i18n.language);

  const formatTs = (value: string) => {
    if (!value) {
      return '—';
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return value;
    }
    return parsed.toLocaleString(i18n.language);
  };

  const volumeItems: ChartItem[] = [
    { label: t('stats.patients'), value: stats.patients, color: chartColor(0) },
    { label: t('stats.studies'), value: stats.studies, color: chartColor(1) },
    { label: t('stats.series'), value: stats.series, color: chartColor(2) },
    { label: t('stats.instances'), value: stats.instances, color: chartColor(3) },
  ];

  const modalityItems: ChartItem[] = stats.studies_by_modality.map((row, index) => ({
    label: row.modality,
    value: row.studies,
    color: chartColor(index),
  }));

  const ageItems: ChartItem[] = stats.study_date_age
    .filter(row => row.count > 0)
    .map((row, index) => ({
      label: row.label,
      value: row.count,
      color: chartColor(index + 2),
    }));

  const diskSegments: DonutSegment[] = stats.disk
    .filter(row => row.mb > 0)
    .map((row, index) => ({
      label: row.label,
      value: row.mb,
      color: chartColor(index),
    }));

  return (
    <div className="flex w-full max-w-full flex-col gap-2 overflow-hidden sm:gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium">{t('stats.title')}</p>
        <p className="text-muted-foreground text-xs">
          {t('stats.updated', { date: formatTs(stats.generated_at) })}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <StatCard
          label={t('stats.patients')}
          value={formatCount(stats.patients)}
        />
        <StatCard
          label={t('stats.studies')}
          value={formatCount(stats.studies)}
        />
        <StatCard
          label={t('stats.series')}
          value={formatCount(stats.series)}
        />
        <StatCard
          label={t('stats.instances')}
          value={formatCount(stats.instances)}
        />
      </div>

      <div className={`grid w-full max-w-full gap-4 ${compact ? 'grid-cols-1' : 'grid-cols-1 xl:grid-cols-2'}`}>
        <div className="border-border rounded-lg border p-3">
          <p className="mb-3 text-xs font-medium">{t('stats.volume')}</p>
          <HorizontalBarChart items={volumeItems} />
        </div>

        <div className="border-border rounded-lg border p-3">
          <p className="mb-3 text-xs font-medium">{t('stats.byModality')}</p>
          <HorizontalBarChart items={modalityItems} />
        </div>

        {!compact ? (
          <>
            <div className="border-border rounded-lg border p-3">
              <p className="mb-3 text-xs font-medium">{t('stats.studyAge')}</p>
              <HorizontalBarChart items={ageItems} />
            </div>

            <div className="border-border rounded-lg border p-3">
              <p className="mb-3 text-xs font-medium">{t('stats.receivedAge')}</p>
              <HorizontalBarChart
                items={stats.received_age
                  .filter(row => row.count > 0)
                  .map((row, index) => ({
                    label: row.label,
                    value: row.count,
                    color: chartColor(index + 4),
                  }))}
              />
            </div>
          </>
        ) : null}

        <div className={`border-border rounded-lg border p-3 ${compact ? '' : 'xl:col-span-2'}`}>
          <p className="mb-3 text-xs font-medium">{t('stats.diskUsage')}</p>
          <DonutChart
            segments={diskSegments}
            centerLabel={t('stats.total')}
            centerValue={`${stats.disk_total_mb.toLocaleString(i18n.language)} MB`}
          />
        </div>
      </div>
    </div>
  );
}
