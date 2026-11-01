import React from 'react';
import { Stamp, FlagStamp } from './primitives/Stamp';

interface StatusBadgeProps {
  status: 'COMPLIED' | 'PENDING' | 'UNVERIFIED' | string;
  size?: 'sm' | 'md' | 'lg';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, size = 'md' }) => {
  const stampSize = size === 'lg' ? 'md' : 'sm';
  return <Stamp status={status} size={stampSize} />;
};

interface OverdueBadgeProps {
  size?: 'sm' | 'md';
}

export const OverdueBadge: React.FC<OverdueBadgeProps> = () => {
  return <FlagStamp flag="overdue_no_record" />;
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
      {flags.overdue_no_record && <FlagStamp flag="overdue_no_record" />}
      {flags.contempt_filed && <FlagStamp flag="contempt_filed" />}
      {flags.extension_sought && <FlagStamp flag="extension_sought" />}
      {flags.contempt_dismissed_for_default && <FlagStamp flag="contempt_dismissed_for_default" />}
    </div>
  );
};
