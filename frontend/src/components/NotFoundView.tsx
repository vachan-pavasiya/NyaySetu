import React from 'react';

interface NotFoundViewProps {
  onReturnToDashboard: () => void;
}

export const NotFoundView: React.FC<NotFoundViewProps> = ({ onReturnToDashboard }) => {
  return (
    <div className="py-20 border border-[var(--border-rule)] bg-[var(--bg-surface)] p-8 max-w-2xl mx-auto my-12 text-center">
      <div className="font-mono text-xs uppercase tracking-widest text-[var(--accent-oxblood)] font-bold mb-2">
        Error 404 · Record Not Found
      </div>
      <h2 className="font-serif text-2xl font-bold text-[var(--ink-primary)] mb-3">
        The requested proceeding or section does not exist in this register.
      </h2>
      <p className="font-sans text-sm text-[var(--ink-secondary)] mb-6 max-w-md mx-auto">
        No judicial record or publication matches this reference.
      </p>
      <button
        onClick={onReturnToDashboard}
        className="font-mono text-xs uppercase tracking-wider font-semibold px-4 py-2 border border-[var(--ink-primary)] bg-[var(--ink-primary)] text-[var(--bg-paper)] hover:bg-[var(--accent-oxblood)] hover:border-[var(--accent-oxblood)] transition-colors rounded-[2px]"
      >
        Return to Principal Register (Dashboard)
      </button>
    </div>
  );
};

