import React from 'react';

interface PageHeaderProps {
  title: string;
  deck?: string;
  volumeOrMeta?: string;
  actions?: React.ReactNode;
  className?: string;
}

export const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  deck,
  volumeOrMeta,
  actions,
  className = '',
}) => {
  return (
    <header className={`border-b border-[var(--border-rule-strong)] pb-3 mb-5 ${className}`}>
      <div className="flex flex-col md:flex-row md:items-baseline md:justify-between gap-2">
        <div>
          {volumeOrMeta && (
            <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--accent-oxblood)] font-semibold mb-0.5">
              {volumeOrMeta}
            </div>
          )}
          <h1 className="font-serif text-2xl font-bold tracking-tight text-[var(--ink-primary)]">
            {title}
          </h1>
          {deck && (
            <p className="font-sans text-[13px] text-[var(--ink-secondary)] mt-1 max-w-3xl leading-snug">
              {deck}
            </p>
          )}
        </div>
        {actions && <div className="flex items-center gap-2 shrink-0 mt-2 md:mt-0">{actions}</div>}
      </div>
    </header>
  );
};

