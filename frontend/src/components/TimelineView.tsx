import React, { useState, useEffect } from 'react';
import type { TimelineEvent } from '../types';
import { getApiUrl } from '../config';
import { PageHeader } from './primitives/PageHeader';
import { HighlightedQuote } from './primitives/Quote';
import { IconExternalLink } from './primitives/Icon';

interface TimelineViewProps {
  initialCaseNumber?: string;
  onSelectJudgment?: (judgmentId: number) => void;
}

export const TimelineView: React.FC<TimelineViewProps> = ({
  initialCaseNumber,
  onSelectJudgment,
}) => {
  const sampleCases = [
    { caseNo: 'MAT/408/2022', label: 'MAT 408 of 2022 (Linked: CPAN 886 of 2022)' },
    { caseNo: 'FMA/1879/2019', label: 'FMA 1879 of 2019 (Linked: CPAN 1261 of 2019)' },
    { caseNo: 'WPA/2222/2022', label: 'WPA 2222 of 2022 (Linked: CPAN 1262 of 2022)' },
    { caseNo: 'WPA/5477/2022', label: 'WPA 5477 of 2022 (Linked: CPAN 1263 of 2022)' },
    { caseNo: 'WPA/7971/2021', label: 'WPA 7971 of 2021 (Linked: CPAN 926 of 2022)' },
    { caseNo: 'WPA/17378/2022', label: 'WPA 17378 of 2022 (Linked: CPAN 810 of 2023)' },
    { caseNo: 'WPA/4466/2022', label: 'WPA 4466 of 2022 (Linked: CPAN 446 of 2023)' },
    { caseNo: 'WPA/18860/2021', label: 'WPA 18860 of 2021 (Linked: CPAN 222 of 2023)' },
  ];

  const [selectedCase, setSelectedCase] = useState<string>(initialCaseNumber || sampleCases[0].caseNo);
  const [timelineData, setTimelineData] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initialCaseNumber) {
      setSelectedCase(initialCaseNumber);
    }
  }, [initialCaseNumber]);

  const fetchTimeline = async (caseNumber: string) => {
    setLoading(true);
    setError(null);
    try {
      const encoded = encodeURIComponent(caseNumber);
      const res = await fetch(getApiUrl(`/cases/${encoded}/timeline`));
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data = await res.json();
      setTimelineData(data);
    } catch (err: any) {
      console.error('Failed to fetch timeline:', err);
      setError(err.message || 'Failed to load case progression timeline');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTimeline(selectedCase);
  }, [selectedCase]);

  return (
    <div className="space-y-6">
      <PageHeader
        volumeOrMeta="Chronological Proceeding Register · High Court Orders"
        title="Case Compliance Timeline"
        deck="Chronological audit tracing original operative orders to subsequent contempt petitions and compliance findings."
        actions={
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs text-[var(--ink-secondary)]">Case:</span>
            <select
              value={selectedCase}
              onChange={(e) => setSelectedCase(e.target.value)}
              className="px-2.5 py-1.5 font-mono text-xs border border-[var(--border-rule-strong)] bg-[var(--bg-surface)] text-[var(--ink-primary)] rounded-[2px] focus:outline-none focus:ring-1 focus:ring-[var(--accent-oxblood)]"
            >
              {!sampleCases.some((c) => c.caseNo === selectedCase) && (
                <option value={selectedCase}>{selectedCase}</option>
              )}
              {sampleCases.map((c) => (
                <option key={c.caseNo} value={c.caseNo}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>
        }
      />

      {loading ? (
        <div className="py-20 border border-[var(--border-rule)] bg-[var(--bg-surface)] text-center font-sans text-xs text-[var(--ink-secondary)] italic">
          Tracing case progression and citation linkages...
        </div>
      ) : error ? (
        <div className="p-4 border border-[var(--status-overdue)] bg-[var(--status-overdue-bg)] text-center font-sans text-xs text-[var(--status-overdue)]">
          {error}
        </div>
      ) : timelineData ? (
        <div className="space-y-6">
          {/* Case Metadata Strip */}
          <div className="border border-[var(--border-rule)] bg-[var(--bg-surface)] p-3 flex flex-wrap items-baseline justify-between gap-3 font-mono text-xs">
            <div className="flex items-baseline gap-3 flex-wrap">
              <span className="font-bold text-sm text-[var(--ink-primary)]">
                {timelineData.case_number}
              </span>
              <span className="text-[var(--ink-secondary)]">
                {timelineData.events?.length || 0} Linked Proceedings
              </span>
            </div>
            <div className="text-[10px] text-[var(--ink-muted)] uppercase">
              Provenance: Verified Header Citations &amp; S3 Orders
            </div>
          </div>

          {/* Vertical Ruled Timeline */}
          <div className="relative pl-6 sm:pl-8 space-y-8 before:absolute before:left-2 sm:before:left-3 before:top-2 before:bottom-2 before:w-[1px] before:bg-[var(--border-rule-strong)]">
            {(timelineData.events || []).map((ev: TimelineEvent, idx: number) => {
              const isContempt = (ev.event_type || '').includes('CONTEMPT');

              return (
                <div key={idx} className="relative space-y-2">
                  {/* Timeline Node Stamp */}
                  <div
                    className={`absolute -left-6 sm:-left-8 top-1.5 w-2.5 h-2.5 rounded-none border border-[var(--ink-primary)] ${
                      isContempt ? 'bg-[var(--accent-oxblood)]' : 'bg-[var(--ink-primary)]'
                    }`}
                  />

                  {/* Event Box */}
                  <div className="border border-[var(--border-rule)] bg-[var(--bg-surface)] p-4 space-y-3">
                    {/* Header: Date, Event Type, Case No */}
                    <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-[var(--border-rule)] pb-2">
                      <div className="flex items-baseline gap-2 flex-wrap">
                        {/* Date in Mono */}
                        <span className="font-mono text-xs font-bold text-[var(--ink-primary)] tabular-nums">
                          {ev.date || 'Date Unrecorded'}
                        </span>
                        {/* Order Type in Small Caps */}
                        <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--accent-oxblood)] font-semibold border-b border-[var(--accent-oxblood)] pb-0.2">
                          {(ev.event_type || 'PROCEEDING').replace(/_/g, ' ')}
                        </span>
                      </div>

                      <div className="flex items-center gap-2">
                        {ev.confidence && (
                          <span className="font-mono text-[10px] text-[var(--ink-muted)] uppercase">
                            Conf: {ev.confidence}
                          </span>
                        )}
                        {onSelectJudgment && ev.judgment_id && (
                          <button
                            onClick={() => onSelectJudgment(ev.judgment_id!)}
                            className="font-mono text-[10px] text-[var(--accent-oxblood)] hover:underline inline-flex items-center gap-1"
                          >
                            Inspect Order <IconExternalLink size={10} />
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Parties & Case Title */}
                    <div>
                      {ev.case_number && (
                        <div className="font-mono font-semibold text-xs text-[var(--ink-primary)]">
                          {ev.case_number}
                        </div>
                      )}
                      {ev.title && (
                        <div className="font-serif italic text-xs text-[var(--ink-secondary)] mt-0.5">
                          {ev.title}
                        </div>
                      )}
                    </div>

                    {/* Summary / Description */}
                    {ev.description && (
                      <p className="font-sans text-xs text-[var(--ink-primary)] leading-relaxed">
                        {ev.description}
                      </p>
                    )}

                    {/* Verbatim Quote in Left-Ruled Indented Block */}
                    {ev.verified_quote && (
                      <HighlightedQuote
                        quote={ev.verified_quote}
                        sourceCase={ev.case_number}
                        sourceDate={ev.date}
                      />
                    )}

                    {/* Verifier Annotations */}
                    {ev.verified_quote && (
                      <div className="pt-1 font-mono text-[10px] text-[var(--status-complied)] font-semibold">
                        Verbatim Quote Verified in Source Order
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="py-20 border border-[var(--border-rule)] bg-[var(--bg-surface)] text-center font-sans text-xs text-[var(--ink-secondary)] italic">
          Select a case to inspect its chronological compliance timeline.
        </div>
      )}
    </div>
  );
};
