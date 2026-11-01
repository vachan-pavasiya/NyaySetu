import React from 'react';
import { CheckCircle2, Clock, HelpCircle, AlertTriangle, ShieldAlert, ArrowUpRight } from 'lucide-react';

interface StatusBadgeProps {
  status: 'COMPLIED' | 'PENDING' | 'UNVERIFIED' | string;
  size?: 'sm' | 'md' | 'lg';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, size = 'md' }) => {
  const normalized = (status || 'UNVERIFIED').toUpperCase();

  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5 gap-1',
    md: 'text-xs px-2.5 py-1 gap-1.5 font-medium',
    lg: 'text-sm px-3 py-1.5 gap-2 font-semibold',
  }[size];

  if (normalized === 'COMPLIED') {
    return (
      <span
        className={`inline-flex items-center rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 ring-1 ring-emerald-600/20 shadow-xs ${sizeClasses}`}
        title="Verified compliance recorded in later order"
      >
        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
        <span>COMPLIED</span>
      </span>
    );
  }

  if (normalized === 'PENDING') {
    return (
      <span
        className={`inline-flex items-center rounded-full bg-amber-50 text-amber-800 border border-amber-200 ring-1 ring-amber-600/20 shadow-xs ${sizeClasses}`}
        title="Deadline window open or ongoing process in progress"
      >
        <Clock className="w-3.5 h-3.5 text-amber-600 shrink-0" />
        <span>PENDING</span>
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center rounded-full bg-slate-100 text-slate-700 border border-slate-300 ring-1 ring-slate-600/10 shadow-xs ${sizeClasses}`}
      title="No verified subsequent compliance record"
    >
      <HelpCircle className="w-3.5 h-3.5 text-slate-500 shrink-0" />
      <span>UNVERIFIED</span>
    </span>
  );
};

interface OverdueBadgeProps {
  size?: 'sm' | 'md';
}

export const OverdueBadge: React.FC<OverdueBadgeProps> = ({ size = 'sm' }) => {
  const sizeClasses = size === 'sm' ? 'text-2xs px-2 py-0.5 gap-1' : 'text-xs px-2.5 py-1 gap-1.5';
  return (
    <span
      className={`inline-flex items-center rounded-md bg-rose-50 text-rose-700 border border-rose-200 ring-1 ring-rose-600/20 font-medium ${sizeClasses}`}
      title="Deadline window lapsed with no record of compliance"
    >
      <AlertTriangle className="w-3 h-3 text-rose-600 shrink-0" />
      <span>OVERDUE</span>
    </span>
  );
};

interface FlagBadgesProps {
  flags: {
    contempt_filed?: boolean;
    extension_sought?: boolean;
    overdue_no_record?: boolean;
    contempt_dismissed_for_default?: boolean;
  };
}

export const FlagBadges: React.FC<FlagBadgesProps> = ({ flags }) => {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {flags.overdue_no_record && <OverdueBadge size="sm" />}
      {flags.contempt_filed && (
        <span
          className="inline-flex items-center gap-1 rounded-md bg-purple-50 text-purple-700 border border-purple-200 text-2xs px-2 py-0.5 font-medium"
          title="Contempt petition filed alleging non-compliance"
        >
          <ShieldAlert className="w-3 h-3 text-purple-600 shrink-0" />
          <span>CONTEMPT FILED</span>
        </span>
      )}
      {flags.extension_sought && (
        <span
          className="inline-flex items-center gap-1 rounded-md bg-blue-50 text-blue-700 border border-blue-200 text-2xs px-2 py-0.5 font-medium"
          title="Extension of time sought by contemnors"
        >
          <ArrowUpRight className="w-3 h-3 text-blue-600 shrink-0" />
          <span>EXTENSION SOUGHT</span>
        </span>
      )}
      {flags.contempt_dismissed_for_default && (
        <span
          className="inline-flex items-center gap-1 rounded-md bg-orange-50 text-orange-700 border border-orange-200 text-2xs px-2 py-0.5 font-medium"
          title="Contempt dismissed for default (petitioner absent); does not prove compliance"
        >
          <AlertTriangle className="w-3 h-3 text-orange-600 shrink-0" />
          <span>DEFAULT DISMISSAL</span>
        </span>
      )}
    </div>
  );
};

