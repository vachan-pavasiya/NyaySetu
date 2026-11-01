import React, { useState, useEffect } from 'react';
import type { JudgmentSummary, JudgmentDetail, DirectionItem } from '../types';
import { StatusBadge, FlagBadges } from './StatusBadge';
import { EvidencePanel } from './EvidencePanel';
import { PageHeader } from './primitives/PageHeader';
import { getApiUrl } from '../config';

interface JudgmentViewProps {
  initialJudgmentId?: number;
}

export const JudgmentView: React.FC<JudgmentViewProps> = ({ initialJudgmentId }) => {
  const [judgments, setJudgments] = useState<JudgmentSummary[]>([]);
  const [selectedJudgment, setSelectedJudgment] = useState<JudgmentDetail | null>(null);
  const [directions, setDirections] = useState<DirectionItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);
  const [activeDirectionId, setActiveDirectionId] = useState<number | null>(null);
  const [searchTerm, setSearchTerm] = useState<string>('');

  const fetchJudgments = async () => {
    setLoading(true);
    try {
      const res = await fetch(getApiUrl('/judgments?limit=200'));
      if (res.ok) {
        const data = await res.json();
        const items: JudgmentSummary[] = data.items || [];
        setJudgments(items);

        if (items.length > 0) {
          const targetId = initialJudgmentId || items[0].id;
          const found = items.find((j) => j.id === targetId) || items[0];
          loadJudgmentDetail(found.id);
        }
      }
    } catch (err) {
      console.error('Failed to fetch judgments list:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadJudgmentDetail = async (judgmentId: number) => {
    setLoadingDetail(true);
    setActiveDirectionId(null);
    try {
      const detailRes = await fetch(getApiUrl(`/judgments/${judgmentId}`));
      if (detailRes.ok) {
        const detail: JudgmentDetail = await detailRes.json();
        setSelectedJudgment(detail);
      }

      const dirsRes = await fetch(getApiUrl(`/judgments/${judgmentId}/directions`));
      if (dirsRes.ok) {
        const rawDirs = await dirsRes.json();
        const fullDirs: DirectionItem[] = await Promise.all(
          rawDirs.map(async (d: any) => {
            try {
              const dRes = await fetch(getApiUrl(`/directions/${d.id}`));
              if (dRes.ok) return await dRes.json();
            } catch {
              // fallback
            }
            return {
              ...d,
              compliance_status: d.compliance_status || 'UNVERIFIED',
              status: d.compliance_status || 'UNVERIFIED',
              flags: {
                contempt_filed: false,
                extension_sought: false,
                overdue_no_record: false,
                contempt_dismissed_for_default: false,
              },
            };
          })
        );
        setDirections(fullDirs);
      }
    } catch (err) {
      console.error(`Failed to load judgment detail for ${judgmentId}:`, err);
    } finally {
      setLoadingDetail(false);
    }
  };

  useEffect(() => {
    fetchJudgments();
  }, [initialJudgmentId]);

  const scrollToQuote = (dirId: number) => {
    setActiveDirectionId(dirId);
    const element = document.getElementById(`quote-${dirId}`);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  };

  const filteredJudgments = judgments.filter(
    (j) =>
      j.case_number.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (j.petitioner && j.petitioner.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (j.respondent && j.respondent.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  const renderTextWithHighlights = () => {
    if (!selectedJudgment?.text) {
      return (
        <div className="py-20 text-center font-sans text-xs text-[var(--ink-secondary)] italic">
          {selectedJudgment?.status.includes('FAIL')
            ? `Order text unreadable: ${selectedJudgment.status}. Marked FAILED_UNREADABLE.`
            : 'No digital text record available for this judgment.'}
        </div>
      );
    }

    const fullText = selectedJudgment.text;

    interface QuoteSpan {
      start: number;
      end: number;
      directionId: number;
      directionIndex: number;
      quote: string;
    }

    const spans: QuoteSpan[] = [];

    directions.forEach((d, idx) => {
      if (!d.source_quote || d.source_quote.trim().length < 5) return;
      const rawQuote = d.source_quote.trim();
      const pos = fullText.indexOf(rawQuote);
      if (pos !== -1) {
        spans.push({
          start: pos,
          end: pos + rawQuote.length,
          directionId: d.id,
          directionIndex: idx + 1,
          quote: rawQuote,
        });
      } else {
        const sub = rawQuote.slice(0, 50);
        const subPos = fullText.indexOf(sub);
        if (subPos !== -1) {
          spans.push({
            start: subPos,
            end: subPos + sub.length,
            directionId: d.id,
            directionIndex: idx + 1,
            quote: sub,
          });
        }
      }
    });

    spans.sort((a, b) => a.start - b.start);

    const nonOverlapping: QuoteSpan[] = [];
    let lastEnd = -1;
    for (const span of spans) {
      if (span.start >= lastEnd) {
        nonOverlapping.push(span);
        lastEnd = span.end;
      }
    }

    const elements: React.ReactNode[] = [];
    let cursor = 0;

    nonOverlapping.forEach((span, i) => {
      if (span.start > cursor) {
        elements.push(
          <span key={`text-${cursor}`}>{fullText.slice(cursor, span.start)}</span>
        );
      }

      const isActive = activeDirectionId === span.directionId;

      elements.push(
        <mark
          key={`mark-${span.directionId}-${i}`}
          id={`quote-${span.directionId}`}
          onClick={() => setActiveDirectionId(span.directionId)}
          title={`Focus Operative Direction #${span.directionIndex}`}
          className={`cursor-pointer px-1 py-0.2 select-text font-serif ${
            isActive
              ? 'bg-[var(--accent-oxblood)] text-white border-none'
              : 'bg-[var(--highlight-pen)] text-[var(--highlight-pen-text)] border-b border-[var(--highlight-pen-border)]'
          }`}
          style={{ borderRadius: 0 }}
        >
          <span className="font-mono text-[9px] uppercase tracking-wider font-bold mr-1 select-none">
            [Dir #{span.directionIndex}]
          </span>
          {fullText.slice(span.start, span.end)}
        </mark>
      );

      cursor = span.end;
    });

    if (cursor < fullText.length) {
      elements.push(<span key="text-end">{fullText.slice(cursor)}</span>);
    }

    return (
      <div className="font-serif text-[13px] leading-[1.75] text-[var(--ink-primary)] whitespace-pre-wrap select-text law-report-text max-w-prose">
        {elements}
      </div>
    );
  };

  return (
    <div className="space-y-6">
      <PageHeader
        volumeOrMeta="Calcutta High Court Law Report View"
        title="Judgment Text &amp; Verbatim Directions"
        deck="Official judgment text annotated with extracted operative mandates. Click any direction margin note to highlight its source in the order."
        actions={
          <button
            onClick={() => window.print()}
            className="font-mono text-xs uppercase tracking-wider font-semibold px-3 py-1.5 border border-[var(--border-rule-strong)] bg-[var(--bg-surface)] hover:bg-[var(--bg-surface-muted)] text-[var(--ink-primary)] rounded-[2px]"
          >
            Print Law Report
          </button>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Index Rail: Judgments List (4 cols) */}
        <div className="lg:col-span-4 border border-[var(--border-rule)] bg-[var(--bg-surface)] no-print">
          <div className="p-3 border-b border-[var(--border-rule)] space-y-2 bg-[var(--bg-surface-muted)]">
            <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--ink-secondary)] font-semibold flex items-center justify-between">
              <span>Ingested Orders ({judgments.length})</span>
            </div>
            <div className="relative">
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Filter case or party..."
                className="w-full px-2 py-1 font-sans text-xs border border-[var(--border-rule-strong)] bg-[var(--bg-paper)] text-[var(--ink-primary)] rounded-[2px] focus:outline-none focus:ring-1 focus:ring-[var(--accent-oxblood)]"
              />
            </div>
          </div>

          <div className="divide-y divide-[var(--border-rule)] max-h-[700px] overflow-y-auto">
            {loading ? (
              <div className="py-12 text-center font-sans text-xs text-[var(--ink-secondary)] italic">
                Loading judgments list...
              </div>
            ) : filteredJudgments.length === 0 ? (
              <div className="py-12 text-center font-sans text-xs text-[var(--ink-secondary)] italic">
                No orders matched the filter.
              </div>
            ) : (
              filteredJudgments.map((j) => {
                const isSelected = selectedJudgment?.id === j.id;
                return (
                  <div
                    key={j.id}
                    onClick={() => loadJudgmentDetail(j.id)}
                    className={`p-3 cursor-pointer transition-colors ${
                      isSelected
                        ? 'bg-[var(--bg-paper)] border-l-2 border-[var(--accent-oxblood)]'
                        : 'hover:bg-[var(--bg-surface-muted)]'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1">
                      <span className="font-mono font-bold text-xs text-[var(--ink-primary)]">
                        {j.case_number}
                      </span>
                      {j.judgment_date && (
                        <span className="font-mono text-[10px] text-[var(--ink-muted)]">
                          {j.judgment_date}
                        </span>
                      )}
                    </div>
                    {(j.petitioner || j.respondent) && (
                      <div className="font-serif text-xs text-[var(--ink-secondary)] truncate mt-1">
                        {j.petitioner || 'Petitioner'} v. {j.respondent || 'State of West Bengal'}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Center & Right: Law Report & Margin Notes (8 cols) */}
        <div className="lg:col-span-8 space-y-6">
          {loadingDetail ? (
            <div className="py-24 border border-[var(--border-rule)] bg-[var(--bg-surface)] text-center font-sans text-xs text-[var(--ink-secondary)] italic">
              Loading law report text and verified operative directions...
            </div>
          ) : selectedJudgment ? (
            <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
              {/* Main Law Report Body (7 cols) */}
              <div className="md:col-span-7 border border-[var(--border-rule)] bg-[var(--bg-surface)] p-6 space-y-5">
                {/* Official Law Report Heading */}
                <div className="border-b border-[var(--border-rule-strong)] pb-4 space-y-1.5 text-center">
                  <div className="font-mono text-[10px] uppercase tracking-widest text-[var(--ink-muted)]">
                    In the High Court of Judicature at Calcutta
                  </div>
                  <div className="font-mono text-xs uppercase tracking-wider text-[var(--ink-secondary)]">
                    Appellate Side · Writ Jurisdiction
                  </div>
                  <h2 className="font-mono font-bold text-base text-[var(--ink-primary)] pt-1">
                    {selectedJudgment.case_number}
                  </h2>
                  {(selectedJudgment.petitioner || selectedJudgment.respondent) && (
                    <div className="font-serif italic text-sm text-[var(--ink-primary)] pt-1">
                      {selectedJudgment.petitioner || 'Petitioner'}
                      <div className="font-sans text-[11px] not-italic text-[var(--ink-muted)] my-0.5">
                        — versus —
                      </div>
                      {selectedJudgment.respondent || 'State of West Bengal &amp; Ors.'}
                    </div>
                  )}
                  {selectedJudgment.judgment_date && (
                    <div className="font-mono text-[11px] text-[var(--accent-oxblood)] font-semibold pt-1">
                      Date of Order: {selectedJudgment.judgment_date}
                    </div>
                  )}
                </div>

                {/* Body Text */}
                <div className="pt-2">{renderTextWithHighlights()}</div>
              </div>

              {/* Right Column: Direction Margin Notes (5 cols) */}
              <div className="md:col-span-5 space-y-4">
                <div className="border border-[var(--border-rule)] bg-[var(--bg-surface)] p-3">
                  <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--ink-secondary)] font-semibold border-b border-[var(--border-rule)] pb-1 mb-2">
                    Operative Directions ({directions.length})
                  </div>

                  {directions.length === 0 ? (
                    <div className="py-6 text-center font-sans text-xs text-[var(--ink-secondary)] italic">
                      No operative mandates were extracted from this judgment order.
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {directions.map((dir, idx) => {
                        const isActive = activeDirectionId === dir.id;
                        return (
                          <div
                            key={dir.id}
                            onClick={() => scrollToQuote(dir.id)}
                            className={`p-3 border transition-colors cursor-pointer space-y-2 ${
                              isActive
                                ? 'border-[var(--accent-oxblood)] bg-[var(--bg-surface-muted)]'
                                : 'border-[var(--border-rule)] bg-[var(--bg-paper)] hover:bg-[var(--bg-surface-muted)]'
                            }`}
                          >
                            <div className="flex items-center justify-between gap-1">
                              <span className="font-mono text-[10px] font-bold text-[var(--accent-oxblood)] uppercase">
                                Direction #{idx + 1}
                              </span>
                              <StatusBadge status={dir.compliance_status || dir.status} size="sm" />
                            </div>

                            <div className="font-serif font-bold text-xs text-[var(--ink-primary)]">
                              {dir.responsible_party}
                            </div>

                            <div className="font-sans text-xs text-[var(--ink-secondary)] leading-snug">
                              {dir.action}
                            </div>

                            {dir.deadline_window_end && (
                              <div className="font-mono text-[10px] text-[var(--ink-secondary)] tabular-nums">
                                Deadline Window: {dir.deadline_window_start} to {dir.deadline_window_end}
                              </div>
                            )}

                            {dir.flags && <FlagBadges flags={dir.flags} />}

                            {dir.source_quote && (
                              <button
                                type="button"
                                className="font-mono text-[10px] text-[var(--accent-oxblood)] hover:underline pt-1 inline-block"
                              >
                                Focus highlighted quote in text →
                              </button>
                            )}

                            {/* Linked evidence items if present */}
                            {dir.evidence && dir.evidence.length > 0 && (
                              <div className="pt-2 border-t border-[var(--border-rule)]">
                                <EvidencePanel evidence={dir.evidence} title="Linked Evidence" />
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="py-24 border border-[var(--border-rule)] bg-[var(--bg-surface)] text-center font-sans text-xs text-[var(--ink-secondary)] italic">
              Select a judgment order from the left register to inspect.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
