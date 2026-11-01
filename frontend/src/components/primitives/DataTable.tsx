import React from 'react';

interface DataTableProps {
  children: React.ReactNode;
  className?: string;
}

export const DataTable: React.FC<DataTableProps> = ({ children, className = '' }) => {
  return (
    <div className={`overflow-x-auto border border-[var(--border-rule)] bg-[var(--bg-surface)] ${className}`}>
      <table className="w-full text-left border-collapse font-sans text-xs">
        {children}
      </table>
    </div>
  );
};

export const TableHead: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = '',
}) => {
  return (
    <thead
      className={`sticky top-0 z-10 bg-[var(--bg-surface-muted)] border-b border-[var(--border-rule-strong)] font-mono text-[10px] uppercase tracking-wider text-[var(--ink-secondary)] ${className}`}
    >
      {children}
    </thead>
  );
};

export const TableRow: React.FC<{
  children: React.ReactNode;
  onClick?: () => void;
  className?: string;
  isClickable?: boolean;
}> = ({ children, onClick, className = '', isClickable = false }) => {
  return (
    <tr
      onClick={onClick}
      className={`border-b border-[var(--border-rule)] hover:bg-[var(--bg-surface-muted)] transition-colors ${
        isClickable ? 'cursor-pointer' : ''
      } ${className}`}
    >
      {children}
    </tr>
  );
};

export const TableCell: React.FC<{
  children?: React.ReactNode;
  className?: string;
  align?: 'left' | 'center' | 'right';
}> = ({ children, className = '', align = 'left' }) => {
  const alignClass = align === 'right' ? 'text-right' : align === 'center' ? 'text-center' : 'text-left';

  return (
    <td className={`py-2 px-3 align-top leading-tight text-[13px] ${alignClass} ${className}`}>
      {children}
    </td>
  );
};

export const TableHeaderCell: React.FC<{
  children?: React.ReactNode;
  className?: string;
  align?: 'left' | 'center' | 'right';
}> = ({ children, className = '', align = 'left' }) => {
  const alignClass = align === 'right' ? 'text-right' : align === 'center' ? 'text-center' : 'text-left';

  return (
    <th className={`py-2 px-3 font-semibold ${alignClass} ${className}`}>
      {children}
    </th>
  );
};
