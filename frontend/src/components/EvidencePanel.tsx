import React from 'react';
import type { EvidenceItem } from '../types';
import { HighlightedQuote } from './primitives/Quote';
import { EvidenceStamp } from './primitives/Stamp';

interface EvidencePanelProps {
  evidence: EvidenceItem[];
  title?: string;
}

export const EvidencePanel: React.FC<EvidencePanelProps> = ({
  evidence,
  title = 'Verified Compliance Evidence',
}) => {
  if (!evidence || evidence.length === 0) {
    return (
      <div className="border border-[var(--border-rule)] bg-[var(--bg-surface-muted)] p-3 font-sans text-xs text-[var(--ink-secondary)] italic">
        No subsequent compliance order or evidence recorded in the public registry for this direction.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {title && (
        <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--ink-secondary)] font-semibold border-b border-[var(--border-rule)] pb-1">
          {title} ({evidence.length})
        </div>
      )}

      {evidence.map((ev) => {
        const isCaseLevel = ev.evidence_scope === 'CASE_LEVEL';

        return (
          <div
            key={ev.id}
            className="border border-[var(--border-rule)] bg-[var(--bg-surface)] p-3 space-y-2.5"
          >
            {/* Header: Source Case & Meta */}
            <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-[var(--border-rule)] pb-2">
              <div className="flex items-baseline gap-2 flex-wrap">
                <span className="font-serif font-bold text-sm text-[var(--ink-primary)]">
                  {ev.source_case_number || 'Linked Subsequent Order'}
                </span>
                {ev.source_date && (
                  <span className="font-mono text-xs text-[var(--ink-secondary)]">
                    dated {ev.source_date}
                  </span>
                )}
              </div>

              <div className="flex items-center gap-1.5 flex-wrap">
                <EvidenceStamp strength={ev.evidence_strength} scope={ev.evidence_scope} />

                {/* Verifier Badge */}
                {ev.verified ? (
                  <span
                    className="font-mono text-[9px] uppercase tracking-wider border border-[var(--status-complied)] text-[var(--status-complied)] bg-[var(--status-complied-bg)] rounded-[2px] px-1.5 py-0.5 leading-tight font-semibold"
                    title="Exact verbatim substring verified in source High Court judgment text"
                  >
                    VERBATIM VERIFIED
                  </span>
                ) : (
                  <span className="font-mono text-[9px] uppercase tracking-wider border border-[var(--status-overdue)] text-[var(--status-overdue)] bg-[var(--status-overdue-bg)] rounded-[2px] px-1.5 py-0.5 leading-tight">
                    UNVERIFIED QUOTE
                  </span>
                )}
              </div>
            </div>

            {/* Case-Level Scope Annotation */}
            {isCaseLevel && (
              <div className="border-l-2 border-[var(--status-pending)] bg-[var(--status-pending-bg)] p-2 font-sans text-xs text-[var(--ink-secondary)] leading-relaxed">
                <strong className="text-[var(--ink-primary)]">Case-level evidence:</strong> this order disposed proceedings covering {ev.directions_covered_count || 'several'} directions in the matter. It is a general disposition rather than individual point-by-point verification.
              </div>
            )}

            {/* Verbatim Supporting Quote */}
            {ev.supporting_quote && (
              <HighlightedQuote
                quote={ev.supporting_quote}
                sourceCase={ev.source_case_number}
                sourceDate={ev.source_date}
              />
            )}

            {/* Verdict & Reasoning */}
            <div className="space-y-1 font-sans text-xs">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--ink-muted)]">Verdict:</span>
                <span className="font-mono text-xs font-semibold text-[var(--ink-primary)]">
                  {ev.verdict}
                </span>
              </div>
              {ev.reasoning && (
                <p className="text-[var(--ink-secondary)] leading-normal">
                  <span className="font-semibold text-[var(--ink-primary)]">Judicial Finding: </span>
                  {ev.reasoning}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};
