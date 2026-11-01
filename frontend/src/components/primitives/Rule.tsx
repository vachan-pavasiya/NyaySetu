import React from 'react';

interface RuleProps {
  double?: boolean;
  className?: string;
}

export const Rule: React.FC<RuleProps> = ({ double = false, className = '' }) => {
  if (double) {
    return (
      <div className={`my-3 space-y-[2px] ${className}`} aria-hidden="true">
        <div className="h-[1px] w-full bg-[var(--border-rule-strong)]" />
        <div className="h-[1px] w-full bg-[var(--border-rule-strong)]" />
      </div>
    );
  }

  return (
    <div
      className={`h-[1px] w-full bg-[var(--border-rule)] my-3 ${className}`}
      aria-hidden="true"
    />
  );
};

