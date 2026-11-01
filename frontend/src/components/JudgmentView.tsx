import React, { useState, useEffect, useRef } from 'react';
import { RefreshCw, Search, ChevronRight, FileText } from 'lucide-react';
import type { JudgmentSummary, JudgmentDetail, DirectionItem } from '../types';
import { StatusBadge, FlagBadges } from './StatusBadge';
import { EvidencePanel } from './EvidencePanel';
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

  const textContainerRef = useRef<HTMLDivElement>(null);

  // Fetch list of judgments
  const fetchJudgments = async () => {
    setLoading(true);
    try {
      const res = await fetch(getApiUrl('/judgments?limit=200'));
      if (res.ok) {
        const data = await res.json();
        const items: JudgmentSummary[] = data.items || [];
        setJudgments(items);

        // Auto-select initial or first judgment
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

  // Load specific judgment detail (includes full text) + directions
  const loadJudgmentDetail = async (judgmentId: number) => {
    setLoadingDetail(true);
    setActiveDirectionId(null);
    try {
      // 1. Fetch full judgment detail (has text)
      const detailRes = await fetch(getApiUrl(`/judgments/${judgmentId}`));
      if (detailRes.ok) {
        const detail: JudgmentDetail = await detailRes.json();
        setSelectedJudgment(detail);
      }

      // 2. Fetch directions for this judgment
      const dirsRes = await fetch(getApiUrl(`/judgments/${judgmentId}/directions`));
      if (dirsRes.ok) {
        const rawDirs = await dirsRes.json();

        // Fetch detailed direction items with evidence
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

  // Scroll to quote in text container
  const scrollToQuote = (dirId: number) => {
    setActiveDirectionId(dirId);
    const element = document.getElementById(`quote-${dirId}`);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  };

  // Filter judgments in list
  const filteredJudgments = judgments.filter(
    (j) =>
      j.case_number.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (j.petitioner && j.petitioner.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (j.respondent && j.respondent.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  // Render highlighted text with verbatim quotes
  const renderTextWithHighlights = () => {
    if (!selectedJudgment?.text) {
      return (
        <div className="py-16 text-center text-slate-400 italic text-xs">
          {selectedJudgment?.status.includes('FAIL')
            ? `Text extraction failed: ${selectedJudgment.status}. Order marked FAILED_UNREADABLE.`
            : 'No extracted text available for this judgment.'}
        </div>
      );
    }

    const fullText = selectedJudgment.text;

    // Find all quote spans in text
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
        // Fallback: search for first 60 chars of quote
        const sub = rawQuote.slice(0, 60);
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

    // Sort by start offset
    spans.sort((a, b) => a.start - b.start);

    // Filter overlapping spans
    const nonOverlapping: QuoteSpan[] = [];
    let lastEnd = -1;
    for (const span of spans) {
      if (span.start >= lastEnd) {
        nonOverlapping.push(span);
        lastEnd = span.end;
      }
    }

    // Build segments
    const elements: React.ReactNode[] = [];
    let cursor = 0;

    nonOverlapping.forEach((span, i) => {
      // Text before span
      if (span.start > cursor) {
        elements.push(
          <span key={`text-${cursor}`}>{fullText.slice(cursor, span.start)}</span>
        );
      }

      const isActive = activeDirectionId === span.directionId;

      // Highlighted quote span
      elements.push(
        <mark
          key={`mark-${span.directionId}-${i}`}
          id={`quote-${span.directionId}`}
          onClick={() => setActiveDirectionId(span.directionId)}
          title={`Click to focus Direction #${span.directionIndex}`}
          className={`cursor-pointer px-1 py-0.5 rounded transition-all duration-300 font-medium ${
            isActive
              ? 'bg-amber-300 text-amber-950 ring-2 ring-amber-500 shadow-sm font-semibold'
              : 'bg-amber-100 text-amber-900 hover:bg-amber-200 border-b-2 border-amber-400'
          }`}
        >
          <span className="inline-block text-3xs font-mono font-bold bg-amber-400/80 text-amber-950 px-1 py-0.2 rounded mr-1 select-none">
            [Dir #{span.directionIndex}]
          </span>
          {fullText.slice(span.start, span.end)}
        </mark>
      );

      cursor = span.end;
    });

    // Remainder text
    if (cursor < fullText.length) {
      elements.push(
        <span key={`text-end`}>{fullText.slice(cursor)}</span>
      );
    }

    return (
      <div className="font-serif text-xs leading-relaxed text-slate-800 whitespace-pre-wrap select-text">
        {elements}
      </div>
    );
  };

  return (
    <div className="space-y-4 max-w-7xl mx-auto">
      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white p-4 rounded-xl border border-slate-200/80 shadow-xs">
        <div className="flex items-center gap-2">
          <FileText className="w-5 h-5 text-slate-700" />
          <div>
            <h2 className="text-base font-bold text-slate-900">Judgment & Direction Verification</h2>
            <p className="text-2xs text-slate-500">
              Verbatim quotes highlighted in the official High Court text. Click any direction to auto-scroll to its source quote.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Quick judgment search input */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search case no. or party..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="text-xs pl-8 pr-3 py-1.5 rounded-lg border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none w-56"
            />
          </div>

          <button
            onClick={fetchJudgments}
            className="p-1.5 rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50"
            title="Refresh Judgments"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Main 3-column layout: Sidebar, Full Text Pane, Directions Side Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* Col 1: Case Selector Sidebar (3 cols) */}
        <div className="lg:col-span-3 rounded-xl border border-slate-200/80 bg-white p-3 shadow-xs h-[750px] flex flex-col space-y-2">
          <div className="flex items-center justify-between px-1 pb-1 border-b border-slate-100">
            <span className="text-2xs font-bold uppercase tracking-wider text-slate-500">
              Orders ({filteredJudgments.length})
            </span>
          </div>

          {loading ? (
            <div className="py-20 text-center text-xs text-slate-400">
              <RefreshCw className="w-4 h-4 animate-spin mx-auto mb-1 text-slate-400" />
              Loading judgments...
            </div>
          ) : (
            <div className="overflow-y-auto space-y-1 flex-1 pr-1">
              {filteredJudgments.map((j) => {
                const isSelected = selectedJudgment?.id === j.id;
                const isContempt = j.case_number.includes('CPAN') || j.case_number.includes('WPCRC');

                return (
                  <div
                    key={j.id}
                    onClick={() => loadJudgmentDetail(j.id)}
                    className={`p-2.5 rounded-lg border text-left cursor-pointer transition-all ${
                      isSelected
                        ? 'border-slate-900 bg-slate-900 text-white shadow-xs'
                        : 'border-slate-200/60 bg-slate-50/50 hover:bg-slate-100/70 text-slate-900'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1">
                      <span className="font-mono text-xs font-semibold">{j.case_number}</span>
                      {isContempt && (
                        <span className={`text-3xs px-1 rounded font-medium ${
                          isSelected ? 'bg-purple-900/60 text-purple-200 border border-purple-400/40' : 'bg-purple-100 text-purple-800'
                        }`}>
                          Contempt
                        </span>
                      )}
                    </div>
                    <div className={`text-3xs line-clamp-1 mt-0.5 ${isSelected ? 'text-slate-300' : 'text-slate-500'}`}>
                      {j.petitioner || 'Petitioner'} vs {j.respondent || 'Respondent'}
                    </div>
                    <div className={`text-3xs mt-1 flex items-center justify-between ${isSelected ? 'text-slate-400' : 'text-slate-400'}`}>
                      <span>{j.judgment_date || 'Date unknown'}</span>
                      <span className="font-mono">{j.court.split('_')[0]}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Col 2: Full Text View with Highlighted Quotes (5 cols) */}
        <div className="lg:col-span-5 rounded-xl border border-slate-200/80 bg-white p-4 shadow-xs h-[750px] flex flex-col space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <div>
              <span className="text-3xs font-mono uppercase tracking-wider text-slate-400">Order Text</span>
              <h3 className="text-xs font-bold text-slate-900 font-mono">
                {selectedJudgment?.case_number || 'Select a judgment'}
              </h3>
            </div>
            {selectedJudgment?.text_quality !== undefined && (
              <span className="text-3xs font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-700">
                OCR Quality: {(selectedJudgment.text_quality * 100).toFixed(0)}%
              </span>
            )}
          </div>

          <div
            ref={textContainerRef}
            className="overflow-y-auto flex-1 pr-2 p-3 bg-slate-50/50 rounded-lg border border-slate-100 space-y-3"
          >
            {loadingDetail ? (
              <div className="py-24 text-center text-xs text-slate-400">
                <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-slate-400" />
                Loading judgment text...
              </div>
            ) : (
              renderTextWithHighlights()
            )}
          </div>
        </div>

        {/* Col 3: Side Panel with Directions, Explanations, Status, Evidence (4 cols) */}
        <div className="lg:col-span-4 rounded-xl border border-slate-200/80 bg-white p-4 shadow-xs h-[750px] flex flex-col space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-bold text-slate-900 uppercase tracking-wide">
                Operative Directions
              </span>
              <span className="text-2xs font-bold px-2 py-0.5 rounded-full bg-slate-900 text-white font-mono">
                {directions.length}
              </span>
            </div>
            <span className="text-3xs text-slate-400">Click card to jump to quote</span>
          </div>

          <div className="overflow-y-auto flex-1 space-y-3 pr-1">
            {loadingDetail ? (
              <div className="py-24 text-center text-xs text-slate-400">
                <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-slate-400" />
                Loading directions...
              </div>
            ) : directions.length === 0 ? (
              <div className="py-20 text-center text-slate-400 text-xs italic">
                No operative directions found for this order.
              </div>
            ) : (
              directions.map((d, index) => {
                const isActive = activeDirectionId === d.id;

                return (
                  <div
                    key={d.id}
                    onClick={() => scrollToQuote(d.id)}
                    className={`rounded-lg border p-3.5 space-y-2.5 cursor-pointer transition-all ${
                      isActive
                        ? 'border-amber-400 bg-amber-50/40 ring-1 ring-amber-400/80 shadow-xs'
                        : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50/50'
                    }`}
                  >
                    {/* Header */}
                    <div className="flex items-center justify-between gap-1 border-b border-slate-100 pb-1.5">
                      <div className="flex items-center gap-1.5">
                        <span className="flex items-center justify-center w-4 h-4 rounded-full bg-slate-900 text-white text-3xs font-bold">
                          {index + 1}
                        </span>
                        <span className="font-semibold text-2xs text-slate-900 truncate max-w-[140px]">
                          {d.responsible_party}
                        </span>
                      </div>
                      <StatusBadge status={d.compliance_status} size="sm" />
                    </div>

                    {/* Flags */}
                    {d.flags && (
                      <div className="flex flex-wrap gap-1">
                        <FlagBadges flags={d.flags} />
                      </div>
                    )}

                    {/* Action */}
                    <p className="text-2xs text-slate-700 leading-normal font-serif">
                      {d.action}
                    </p>

                    {/* Source Quote snippet with jump button */}
                    <div className="rounded bg-slate-50 p-2 border border-slate-100 text-3xs text-slate-600 font-serif italic flex items-center justify-between gap-2">
                      <span className="line-clamp-2">&ldquo;{d.source_quote}&rdquo;</span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          scrollToQuote(d.id);
                        }}
                        className="p-1 rounded hover:bg-slate-200 text-amber-700 shrink-0"
                        title="Scroll to quote"
                      >
                        <ChevronRight className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    {/* Deadline explanation */}
                    <div className="bg-slate-50/80 p-2 rounded border border-slate-100 text-3xs space-y-1">
                      <div className="flex justify-between items-center text-slate-700">
                        <span className="font-semibold">Deadline Window:</span>
                        <span className="font-mono font-medium">
                          {d.deadline_window_end ? `${d.deadline_window_start || 'Pronounced'} → ${d.deadline_window_end}` : 'No deadline'}
                        </span>
                      </div>
                      {d.explanation_text && (
                        <div className="text-slate-500 italic">
                          {d.explanation_text}
                        </div>
                      )}
                      {d.sub_reason && (
                        <div className="text-slate-600 border-t border-slate-200/60 pt-1 mt-1">
                          <span className="font-semibold text-slate-700">Reason: </span>
                          {d.sub_reason}
                        </div>
                      )}
                    </div>

                    {/* Evidence Panel if any */}
                    {d.evidence && d.evidence.length > 0 && (
                      <div className="pt-1.5 border-t border-slate-100">
                        <EvidencePanel evidence={d.evidence} />
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
