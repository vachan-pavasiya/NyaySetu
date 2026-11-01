import React from 'react';

export type HeadlineStatus = 'COMPLIED' | 'PENDING' | 'UNVERIFIED';

interface StampProps {
  status: HeadlineStatus | string;
  size?: 'sm' | 'md';
  className?: string;
}

export const Stamp: React.FC<StampProps> = ({ status, size = 'sm', className = '' }) => {
  const norm = (status || 'UNVERIFIED').toUpperCase();

  let colorClasses = 'border-[var(--status-unverified)] text-[var(--status-unverified)] bg-[var(--status-unverified-bg)]';
  let label = 'UNVERIFIED';

  if (norm === 'COMPLIED') {
    colorClasses = 'border-[var(--status-complied)] text-[var(--status-complied)] bg-[var(--status-complied-bg)]';
    label = 'COMPLIED';
  } else if (norm === 'PENDING') {
    colorClasses = 'border-[var(--status-pending)] text-[var(--status-pending)] bg-[var(--status-pending-bg)]';
    label = 'PENDING';
  }

  const sizeClasses = size === 'sm'
    ? 'text-[10px] px-1.5 py-0.5 tracking-wider'
    : 'text-[11px] px-2 py-0.75 tracking-widest';

  return (
    <span
      className={`inline-block font-mono font-semibold uppercase border rounded-[2px] leading-tight select-none ${sizeClasses} ${colorClasses} ${className}`}
    >
      {label}
    </span>
  );
};

export const FlagStamp: React.FC<{ flag: string; className?: string }> = ({ flag, className = '' }) => {
  let styleClasses = 'border-[var(--border-rule-strong)] text-[var(--ink-secondary)] bg-[var(--bg-surface-muted)]';
  let label = flag.replace(/_/g, ' ');

  if (flag === 'overdue_no_record' || flag === 'OVERDUE_NO_RECORD') {
    styleClasses = 'border-[var(--status-overdue)] text-[var(--status-overdue)] bg-[var(--status-overdue-bg)]';
    label = 'OVERDUE (NO RECORD)';
  } else if (flag === 'contempt_filed' || flag === 'CONTEMPT_FILED') {
    styleClasses = 'border-[var(--accent-oxblood)] text-[var(--accent-oxblood)] bg-[var(--accent-oxblood-subtle)]';
    label = 'CONTEMPT FILED';
  } else if (flag === 'extension_sought' || flag === 'EXTENSION_SOUGHT') {
    styleClasses = 'border-[var(--status-pending)] text-[var(--status-pending)] bg-[var(--status-pending-bg)]';
    label = 'EXTENSION SOUGHT';
  } else if (flag === 'contempt_dismissed_for_default' || flag === 'CONTEMPT_DISMISSED_FOR_DEFAULT') {
    styleClasses = 'border-[var(--ink-muted)] text-[var(--ink-muted)] bg-[var(--bg-surface-muted)]';
    label = 'DISMISSED FOR DEFAULT';
  }

  return (
    <span
      className={`inline-block font-mono text-[9px] font-semibold uppercase tracking-wider border rounded-[2px] px-1.5 py-0.5 leading-tight select-none ${styleClasses} ${className}`}
    >
      {label}
    </span>
  );
};

export const EvidenceStamp: React.FC<{ strength?: string; scope?: string; className?: string }> = ({
  strength,
  scope,
  className = '',
}) => {
  const isCourt = strength === 'COURT_RECORDED';
  const isCaseLevel = scope === 'CASE_LEVEL';

  return (
    <div className={`inline-flex items-center gap-1.5 flex-wrap ${className}`}>
      {strength && (
        <span
          className={`font-mono text-[9px] font-semibold uppercase tracking-wider border rounded-[2px] px-1.5 py-0.5 leading-tight ${
            isCourt
              ? 'border-[var(--status-complied)] text-[var(--status-complied)] bg-[var(--status-complied-bg)]'
              : 'border-[var(--status-pending)] text-[var(--status-pending)] bg-[var(--status-pending-bg)]'
          }`}
          title={isCourt ? 'Judicial order recorded fact' : 'Party affidavit or advocate assertion'}
        >
          {strength.replace('_', ' ')}
        </span>
      )}
      {isCaseLevel && (
        <span
          className="font-mono text-[9px] font-semibold uppercase tracking-wider border border-[var(--border-rule-strong)] text-[var(--ink-secondary)] bg-[var(--bg-surface-muted)] rounded-[2px] px-1.5 py-0.5 leading-tight"
          title="Case-level order covering multiple operative directions"
        >
          CASE LEVEL
        </span>
      )}
    </div>
  );
};

