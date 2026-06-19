import React from 'react';

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

export function HorizontalBarChart({ items, emptyLabel = 'Sem dados.' }: HorizontalBarChartProps) {
  if (items.length === 0) {
    return <p className="text-muted-foreground text-xs">{emptyLabel}</p>;
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
            <span className="text-right tabular-nums">{item.value.toLocaleString('pt-BR')}</span>
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
    return <p className="text-muted-foreground text-xs">Sem dados de disco.</p>;
  }

  let cursor = 0;
  const gradientParts = segments.map((segment, index) => {
    const start = (cursor / total) * 100;
    cursor += segment.value;
    const end = (cursor / total) * 100;
    const color = segment.color || chartColor(index);
    return `${color} ${start}% ${end}%`;
  });

  return (
    <div className="flex w-full max-w-full flex-col items-stretch gap-4 sm:flex-row sm:items-start">
      <div
        className="relative mx-auto h-32 w-32 shrink-0 rounded-full sm:mx-0"
        style={{ background: `conic-gradient(${gradientParts.join(', ')})` }}
      >
        <div className="bg-background absolute inset-5 flex flex-col items-center justify-center rounded-full text-center">
          <span className="text-lg font-semibold leading-none">{centerValue}</span>
          <span className="text-muted-foreground mt-1 text-[10px] uppercase tracking-wide">
            {centerLabel}
          </span>
        </div>
      </div>
      <div className="grid min-w-0 w-full flex-1 gap-2">
        {segments.map((segment, index) => {
          const pct = ((segment.value / total) * 100).toFixed(1);
          const color = segment.color || chartColor(index);
          return (
            <div
              key={segment.label}
              className="flex items-center justify-between gap-2 text-xs"
            >
              <div className="flex min-w-0 items-center gap-2">
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ backgroundColor: color }}
                />
                <span className="truncate">{segment.label}</span>
              </div>
              <span className="text-muted-foreground tabular-nums">
                {segment.value.toLocaleString('pt-BR', { maximumFractionDigits: 1 })} MB ({pct}%)
              </span>
            </div>
          );
        })}
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

function formatCount(value: number): string {
  return value.toLocaleString('pt-BR');
}

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

export function PacsStatsPanel({ stats, compact = false }: PacsStatsPanelProps) {
  const volumeItems: ChartItem[] = [
    { label: 'Pacientes', value: stats.patients, color: chartColor(0) },
    { label: 'Exames', value: stats.studies, color: chartColor(1) },
    { label: 'Séries', value: stats.series, color: chartColor(2) },
    { label: 'Imagens', value: stats.instances, color: chartColor(3) },
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
        <p className="text-sm font-medium">Estatísticas do servidor</p>
        <p className="text-muted-foreground text-xs">Atualizado {formatTs(stats.generated_at)}</p>
      </div>

      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <StatCard
          label="Pacientes"
          value={formatCount(stats.patients)}
        />
        <StatCard
          label="Exames"
          value={formatCount(stats.studies)}
        />
        <StatCard
          label="Séries"
          value={formatCount(stats.series)}
        />
        <StatCard
          label="Imagens"
          value={formatCount(stats.instances)}
        />
      </div>

      <div className={`grid w-full max-w-full gap-4 ${compact ? 'grid-cols-1' : 'grid-cols-1 xl:grid-cols-2'}`}>
        <div className="border-border rounded-lg border p-3">
          <p className="mb-3 text-xs font-medium">Volume de dados</p>
          <HorizontalBarChart items={volumeItems} />
        </div>

        <div className="border-border rounded-lg border p-3">
          <p className="mb-3 text-xs font-medium">Exames por modalidade</p>
          <HorizontalBarChart items={modalityItems} />
        </div>

        {!compact ? (
          <>
            <div className="border-border rounded-lg border p-3">
              <p className="mb-3 text-xs font-medium">Idade dos exames (data do estudo)</p>
              <HorizontalBarChart items={ageItems} />
            </div>

            <div className="border-border rounded-lg border p-3">
              <p className="mb-3 text-xs font-medium">Idade na ingestão</p>
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
          <p className="mb-3 text-xs font-medium">Utilização de disco</p>
          <DonutChart
            segments={diskSegments}
            centerLabel="Total"
            centerValue={`${stats.disk_total_mb.toLocaleString('pt-BR')} MB`}
          />
        </div>
      </div>
    </div>
  );
}
