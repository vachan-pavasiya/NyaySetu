import React from 'react';

interface LogoProps {
  className?: string;
  size?: 'sm' | 'md' | 'lg';
  showSubtitle?: boolean;
}

export const Logo: React.FC<LogoProps> = ({
  className = '',
  size = 'md',
  showSubtitle = true,
}) => {
  const iconDimensions = size === 'sm' ? 22 : size === 'lg' ? 36 : 28;

  return (
    <div className={`flex items-center gap-3 select-none ${className}`}>
      {/* Geometric single-arch bridge mark */}
      <svg
        width={iconDimensions}
        height={iconDimensions}
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="shrink-0 text-[var(--accent-oxblood)]"
        aria-hidden="true"
      >
        {/* Horizontal roadway */}
        <line
          x1="2"
          y1="11"
          x2="30"
          y2="11"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="square"
        />
        {/* Structural single arch */}
        <path
          d="M4 25 C4 13.5, 28 13.5, 28 25"
          stroke="var(--ink-primary)"
          strokeWidth="2"
          fill="none"
          strokeLinecap="square"
        />
        {/* Balanced vertical struts */}
        <line x1="16" y1="11" x2="16" y2="16" stroke="currentColor" strokeWidth="1.5" />
        <line x1="10" y1="11" x2="10" y2="18.5" stroke="currentColor" strokeWidth="1.5" />
        <line x1="22" y1="11" x2="22" y2="18.5" stroke="currentColor" strokeWidth="1.5" />
        {/* Shoreline pier abutments */}
        <line
          x1="2"
          y1="25"
          x2="7"
          y2="25"
          stroke="var(--ink-primary)"
          strokeWidth="2"
          strokeLinecap="square"
        />
        <line
          x1="25"
          y1="25"
          x2="30"
          y2="25"
          stroke="var(--ink-primary)"
          strokeWidth="2"
          strokeLinecap="square"
        />
      </svg>

      {/* Serif Wordmark */}
      <div className="flex flex-col">
        <div className="flex items-baseline gap-1.5">
          <span className="font-serif font-bold text-lg tracking-tight text-[var(--ink-primary)] leading-none">
            NyaySetu
          </span>
          <span className="font-mono text-[9px] uppercase tracking-wider text-[var(--accent-oxblood)] font-semibold border-b border-[var(--accent-oxblood)] pb-0.5">
            Vol. 2023
          </span>
        </div>
        {showSubtitle && (
          <span className="font-sans text-[11px] tracking-normal text-[var(--ink-secondary)] leading-tight mt-0.5">
            Court-Order Compliance Radar
          </span>
        )}
      </div>
    </div>
  );
};

