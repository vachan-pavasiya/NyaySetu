import React from 'react';

interface MetricFigureProps {
  value: number | string;
  label: string;
  sublabel?: string;
  statusVariant?: 'complied' | 'pending' | 'unverified' | 'neutral' | 'oxblood';
}

export const MetricFigure: React.FC<MetricFigureProps> = ({
  value,
  label,
  sublabel,
  statusVariant = 'neutral',
}) => {
  let color = 'text-[var(--ink-primary)]';
  if (statusVariant === 'complied') color = 'text-[var(--status-complied)]';
  if (statusVariant === 'pending') color = 'text-[var(--status-pending)]';
  if (statusVariant === 'unverified') color = 'text-[var(--status-unverified)]';
  if (statusVariant === 'oxblood') color = 'text-[var(--accent-oxblood)]';

  return (
    <div className="flex-1 min-w-[130px] py-2 px-3 border-r border-[var(--border-rule)] last:border-r-0">
      <div className={`font-serif text-3xl font-bold tracking-tight tabular-nums leading-none ${color}`}>
        {value}
      </div>
      <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--ink-secondary)] font-semibold mt-1">
        {label}
      </div>
      {sublabel && (
        <div className="font-sans text-[11px] text-[var(--ink-muted)] mt-0.5 leading-snug">
          {sublabel}
        </div>
      )}
    </div>
  );
};

export const MetricFigureRow: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = '',
}) => {
  return (
    <div
      className={`border-y border-[var(--border-rule-strong)] bg-[var(--bg-surface)] py-1 flex flex-wrap divide-y md:divide-y-0 ${className}`}
    >
      {children}
    </div>
  );
};

