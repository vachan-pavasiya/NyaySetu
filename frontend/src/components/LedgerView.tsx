import React, { useState, useEffect } from 'react';
import type { LedgerItem, LedgerResponse } from '../types';
import { StatusBadge, FlagBadges } from './StatusBadge';
import { EvidencePanel } from './EvidencePanel';
import { EvidenceStamp } from './primitives/Stamp';
import { PageHeader } from './primitives/PageHeader';
import { DataTable, TableHead, TableRow, TableHeaderCell, TableCell } from './primitives/DataTable';
import { IconDownload, IconChevronRight, IconExternalLink, IconChevronLeft } from './primitives/Icon';
import { getApiUrl } from '../config';

interface LedgerViewProps {
  initialDepartment?: string;
  onSelectJudgment?: (judgmentId: number) => void;
  onSelectCase?: (caseNumber: string) => void;
}

export const LedgerView: React.FC<LedgerViewProps> = ({
  initialDepartment = '',
  onSelectJudgment,
  onSelectCase,
}) => {
  const [items, setItems] = useState<LedgerItem[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [page, setPage] = useState<number>(1);
  const [pageSize] = useState<number>(20);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [bucketFilter, setBucketFilter] = useState<string>('ALL');
  const [departmentFilter, setDepartmentFilter] = useState<string>(initialDepartment);
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [fromDate] = useState<string>('');
  const [toDate] = useState<string>('');
  const [overdueOnly, setOverdueOnly] = useState<boolean>(false);
  const [contemptOnly, setContemptOnly] = useState<boolean>(false);

  // Expanded row ID for evidence panel
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [expandedDetail, setExpandedDetail] = useState<{ [key: number]: any }>({});
  const [loadingDetail, setLoadingDetail] = useState<{ [key: number]: boolean }>({});

  useEffect(() => {
    if (initialDepartment) {
      setDepartmentFilter(initialDepartment);
      setPage(1);
    }
  }, [initialDepartment]);

  const fetchLedger = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (statusFilter !== 'ALL') params.append('status', statusFilter);
      if (bucketFilter !== 'ALL') params.append('bucket', bucketFilter);
      if (departmentFilter.trim()) params.append('department', departmentFilter.trim());
      if (searchTerm.trim()) params.append('search', searchTerm.trim());
      if (fromDate) params.append('from', fromDate);
      if (toDate) params.append('to', toDate);
      if (overdueOnly) params.append('overdue_only', 'true');
      if (contemptOnly) params.append('contempt_only', 'true');

      params.append('page', page.toString());
      params.append('page_size', pageSize.toString());

      const res = await fetch(getApiUrl(`/ledger?${params.toString()}`));
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data: LedgerResponse = await res.json();
      setItems(data.items || []);
      setTotal(data.total || 0);
      setTotalPages(data.total_pages || Math.max(1, Math.ceil((data.total || 0) / pageSize)));
    } catch (err: any) {
      console.error('Failed to fetch ledger:', err);
      setError(err.message || 'Failed to load ledger records');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLedger();
  }, [page, pageSize, statusFilter, bucketFilter, overdueOnly, contemptOnly]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    fetchLedger();
  };

  const handleResetFilters = () => {
    setStatusFilter('ALL');
    setBucketFilter('ALL');
    setDepartmentFilter('');
    setSearchTerm('');
    setOverdueOnly(false);
    setContemptOnly(false);
    setPage(1);
  };

  const toggleExpand = async (id: number) => {
    if (expandedId === id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(id);

    if (!expandedDetail[id]) {
      setLoadingDetail((prev) => ({ ...prev, [id]: true }));
      try {
        const res = await fetch(getApiUrl(`/directions/${id}`));
        if (res.ok) {
          const detail = await res.json();
          setExpandedDetail((prev) => ({ ...prev, [id]: detail }));
        }
      } catch (err) {
        console.error('Failed to load direction detail:', err);
      } finally {
        setLoadingDetail((prev) => ({ ...prev, [id]: false }));
      }
    }
  };

  const handleExportCsv = () => {
    const params = new URLSearchParams();
    if (statusFilter !== 'ALL') params.append('status', statusFilter);
    if (bucketFilter !== 'ALL') params.append('bucket', bucketFilter);
    if (departmentFilter.trim()) params.append('department', departmentFilter.trim());
    if (searchTerm.trim()) params.append('search', searchTerm.trim());
    if (fromDate) params.append('from', fromDate);
    if (toDate) params.append('to', toDate);
    if (overdueOnly) params.append('overdue_only', 'true');
    if (contemptOnly) params.append('contempt_only', 'true');

    window.open(getApiUrl(`/export.csv?${params.toString()}`), '_blank');
  };

  return (
    <div className="space-y-6">
      {/* Editorial Page Header */}
      <PageHeader
        volumeOrMeta="Gazette Compliance Ledger · Calcutta High Court"
        title="Register of Court-Ordered Directions"
        deck="Operative judicial mandates, cleaned government department parties, estimated deadline windows, and verified subsequent order citations."
        actions={
          <button
            onClick={handleExportCsv}
            className="font-mono text-xs uppercase tracking-wider font-semibold px-3 py-1.5 border border-[var(--border-rule-strong)] bg-[var(--bg-surface)] hover:bg-[var(--bg-surface-muted)] text-[var(--ink-primary)] rounded-[2px] inline-flex items-center gap-1.5"
          >
            <IconDownload size={13} />
            <span>Export Ledger CSV</span>
          </button>
        }
      />

      {/* Filter Toolbar */}
      <div className="border border-[var(--border-rule)] bg-[var(--bg-surface)] p-3 space-y-3">
        <form onSubmit={handleSearchSubmit} className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {/* Search Input */}
            <div className="relative">
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search action text or case number..."
                className="w-full px-2.5 py-1.5 font-sans text-xs border border-[var(--border-rule-strong)] bg-[var(--bg-paper)] text-[var(--ink-primary)] placeholder-[var(--ink-muted)] rounded-[2px] focus:outline-none focus:ring-1 focus:ring-[var(--accent-oxblood)]"
              />
            </div>

            {/* Department Filter */}
            <div>
              <input
                type="text"
                value={departmentFilter}
                onChange={(e) => setDepartmentFilter(e.target.value)}
                placeholder="Filter by government department..."
                className="w-full px-2.5 py-1.5 font-sans text-xs border border-[var(--border-rule-strong)] bg-[var(--bg-paper)] text-[var(--ink-primary)] placeholder-[var(--ink-muted)] rounded-[2px] focus:outline-none focus:ring-1 focus:ring-[var(--accent-oxblood)]"
              />
            </div>

            {/* Headline Status Filter */}
            <div>
              <select
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  setPage(1);
                }}
                className="w-full px-2.5 py-1.5 font-mono text-xs border border-[var(--border-rule-strong)] bg-[var(--bg-paper)] text-[var(--ink-primary)] rounded-[2px] focus:outline-none focus:ring-1 focus:ring-[var(--accent-oxblood)]"
              >
                <option value="ALL">All Headline Statuses</option>
                <option value="COMPLIED">COMPLIED</option>
                <option value="PENDING">PENDING</option>
                <option value="UNVERIFIED">UNVERIFIED</option>
              </select>
            </div>

            {/* Deadline Bucket Filter */}
            <div>
              <select
                value={bucketFilter}
                onChange={(e) => {
                  setBucketFilter(e.target.value);
                  setPage(1);
                }}
                className="w-full px-2.5 py-1.5 font-mono text-xs border border-[var(--border-rule-strong)] bg-[var(--bg-paper)] text-[var(--ink-primary)] rounded-[2px] focus:outline-none focus:ring-1 focus:ring-[var(--accent-oxblood)]"
              >
                <option value="ALL">All Deadline Buckets</option>
                <option value="LAPSED">Lapsed Window</option>
                <option value="IN_WINDOW">In-Window</option>
                <option value="UPCOMING">Upcoming</option>
                <option value="DEPENDENT">Dependent on Event</option>
                <option value="AMBIGUOUS">Ambiguous Date</option>
                <option value="NO_DEADLINE">No Deadline Mentioned</option>
              </select>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 pt-1 border-t border-[var(--border-rule)]">
            <div className="flex flex-wrap items-center gap-4 font-sans text-xs text-[var(--ink-secondary)]">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={overdueOnly}
                  onChange={(e) => {
                    setOverdueOnly(e.target.checked);
                    setPage(1);
                  }}
                  className="rounded-[2px] border-[var(--border-rule-strong)] text-[var(--accent-oxblood)]"
                />
                <span>Overdue (No Record) only</span>
              </label>

              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={contemptOnly}
                  onChange={(e) => {
                    setContemptOnly(e.target.checked);
                    setPage(1);
                  }}
                  className="rounded-[2px] border-[var(--border-rule-strong)] text-[var(--accent-oxblood)]"
                />
                <span>Contempt Petitions only</span>
              </label>

              {(departmentFilter || searchTerm || statusFilter !== 'ALL' || bucketFilter !== 'ALL' || overdueOnly || contemptOnly) && (
                <button
                  type="button"
                  onClick={handleResetFilters}
                  className="text-xs text-[var(--accent-oxblood)] hover:underline font-semibold"
                >
                  Clear all filters
                </button>
              )}
            </div>

            <div className="flex items-center gap-2">
              <span className="font-mono text-xs text-[var(--ink-muted)] tabular-nums">
                {total} directions matched
              </span>
              <button
                type="submit"
                className="font-mono text-xs uppercase tracking-wider font-semibold px-3 py-1.5 border border-[var(--ink-primary)] bg-[var(--ink-primary)] text-[var(--bg-paper)] hover:bg-[var(--accent-oxblood)] hover:border-[var(--accent-oxblood)] transition-colors rounded-[2px]"
              >
                Apply Filters
              </button>
            </div>
          </div>
        </form>
      </div>

      {/* Ledger Table */}
      <div className="space-y-3">
        {loading ? (
          <div className="py-20 border border-[var(--border-rule)] bg-[var(--bg-surface)] text-center font-sans text-xs text-[var(--ink-secondary)] italic">
            Querying compliance ledger records...
          </div>
        ) : error ? (
          <div className="p-4 border border-[var(--status-overdue)] bg-[var(--status-overdue-bg)] text-center font-sans text-xs text-[var(--status-overdue)]">
            {error}
          </div>
        ) : items.length === 0 ? (
          <div className="py-20 border border-[var(--border-rule)] bg-[var(--bg-surface)] text-center font-sans text-xs text-[var(--ink-secondary)] italic">
            No operative directions matched the specified criteria.
          </div>
        ) : (
          <DataTable>
            <TableHead>
              <tr>
                <TableHeaderCell className="w-8"></TableHeaderCell>
                <TableHeaderCell>Case Reference &amp; Responsible Authority</TableHeaderCell>
                <TableHeaderCell>Operative Direction Mandate</TableHeaderCell>
                <TableHeaderCell>Estimated Deadline Window</TableHeaderCell>
                <TableHeaderCell align="center">Compliance Status</TableHeaderCell>
                <TableHeaderCell align="center">Evidence Strength</TableHeaderCell>
              </tr>
            </TableHead>
            <tbody>
              {items.map((item) => {
                const isExpanded = expandedId === item.id;
                const detail = expandedDetail[item.id];
                const isLoadingDet = loadingDetail[item.id];

                return (
                  <React.Fragment key={item.id}>
                    <TableRow
                      isClickable
                      onClick={() => toggleExpand(item.id)}
                      className={isExpanded ? 'bg-[var(--bg-surface-muted)]' : ''}
                    >
                      {/* Expand Chevron */}
                      <TableCell className="text-[var(--ink-muted)]">
                        <IconChevronRight
                          size={12}
                          className={`transform transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                        />
                      </TableCell>

                      {/* Case Reference & Authority */}
                      <TableCell>
                        <div className="space-y-0.5">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span
                              className={`font-mono font-bold text-xs text-[var(--ink-primary)] ${
                                onSelectCase && item.case_number ? 'hover:text-[var(--accent-oxblood)] hover:underline cursor-pointer' : ''
                              }`}
                              onClick={(e) => {
                                if (onSelectCase && item.case_number) {
                                  e.stopPropagation();
                                  onSelectCase(item.case_number);
                                }
                              }}
                              title={onSelectCase ? 'View Case Timeline' : undefined}
                            >
                              {item.case_number || 'Case Record'}
                            </span>
                            {item.judgment_date && (
                              <span className="font-mono text-[10px] text-[var(--ink-secondary)]">
                                ({item.judgment_date})
                              </span>
                            )}
                          </div>

                          {/* Cleaned Department */}
                          <div className="font-serif font-bold text-xs text-[var(--ink-primary)]">
                            {item.cleaned_department || item.responsible_party}
                          </div>

                          {/* Raw party text if cleaned */}
                          {item.cleaned_department && item.cleaned_department !== item.responsible_party && (
                            <div
                              className="font-sans text-[10px] text-[var(--ink-muted)] truncate max-w-xs"
                              title={`Raw party name in order: ${item.responsible_party}`}
                            >
                              orig: {item.responsible_party}
                            </div>
                          )}
                        </div>
                      </TableCell>

                      {/* Operative Action */}
                      <TableCell>
                        <div className="font-sans text-xs text-[var(--ink-primary)] line-clamp-2 leading-relaxed">
                          {item.action}
                        </div>
                        {item.deadline_phrase && (
                          <div className="font-mono text-[10px] text-[var(--accent-oxblood)] mt-0.5">
                            phrase: &ldquo;{item.deadline_phrase}&rdquo;
                          </div>
                        )}
                      </TableCell>

                      {/* Deadline Window */}
                      <TableCell>
                        <div className="font-mono text-xs tabular-nums space-y-0.5">
                          {item.deadline_window_start && item.deadline_window_end ? (
                            <div>
                              <span className="text-[var(--ink-primary)] font-semibold">
                                {item.deadline_window_start}
                              </span>
                              <span className="text-[var(--ink-muted)] mx-1">to</span>
                              <span className="text-[var(--ink-primary)] font-semibold">
                                {item.deadline_window_end}
                              </span>
                            </div>
                          ) : (
                            <span className="text-[var(--ink-muted)] italic">Date undefined</span>
                          )}
                          <div className="text-[10px] text-[var(--ink-secondary)] uppercase">
                            {(item.deadline_status || '').replace(/_/g, ' ')}
                          </div>
                        </div>
                      </TableCell>

                      {/* Status & Flags */}
                      <TableCell align="center">
                        <div className="flex flex-col items-center gap-1">
                          <StatusBadge status={item.status} size="sm" />
                          <FlagBadges flags={item.flags} />
                        </div>
                      </TableCell>

                      {/* Evidence */}
                      <TableCell align="center">
                        <EvidenceStamp
                          strength={item.evidence_strength}
                          scope={item.evidence_scope}
                        />
                      </TableCell>
                    </TableRow>

                    {/* Expanded Detail Panel */}
                    {isExpanded && (
                      <tr className="bg-[var(--bg-paper)] border-b border-[var(--border-rule-strong)]">
                        <td colSpan={6} className="p-4 space-y-4">
                          {isLoadingDet ? (
                            <div className="py-4 text-center font-sans text-xs text-[var(--ink-secondary)] italic">
                              Retrieving direction record and verified quotes...
                            </div>
                          ) : detail ? (
                            <div className="space-y-3">
                              {/* Source Quote */}
                              {detail.direction?.source_quote && (
                                <div className="space-y-1">
                                  <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--ink-secondary)] font-semibold">
                                    Operative Quote from Judgment Text
                                  </div>
                                  <div className="border-l-2 border-[var(--accent-oxblood)] bg-[var(--highlight-pen)] text-[var(--highlight-pen-text)] p-3 font-serif text-xs italic leading-relaxed">
                                    &ldquo;{detail.direction.source_quote}&rdquo;
                                  </div>
                                </div>
                              )}

                              {/* Explanation & Service Lag math */}
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-sans">
                                <div className="border border-[var(--border-rule)] bg-[var(--bg-surface)] p-3 space-y-1">
                                  <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--ink-muted)] font-semibold">
                                    Deterministic Deadline Window Explanation
                                  </div>
                                  <p className="text-[var(--ink-secondary)] leading-relaxed">
                                    {detail.direction?.deadline_explanation ||
                                      'Order receipt date is unrecorded. Calculated as [order_date + N, order_date + N + 30 days service lag].'}
                                  </p>
                                </div>

                                <div className="border border-[var(--border-rule)] bg-[var(--bg-surface)] p-3 space-y-1">
                                  <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--ink-muted)] font-semibold">
                                    Record References &amp; Timeline
                                  </div>
                                  <div className="flex items-center gap-3 pt-1">
                                    {onSelectJudgment && detail.direction?.judgment_id && (
                                      <button
                                        onClick={() => onSelectJudgment(detail.direction.judgment_id)}
                                        className="font-mono text-xs text-[var(--accent-oxblood)] hover:underline inline-flex items-center gap-1"
                                      >
                                        Inspect Source Judgment <IconExternalLink size={10} />
                                      </button>
                                    )}
                                    {onSelectCase && item.case_number && (
                                      <button
                                        onClick={() => onSelectCase(item.case_number!)}
                                        className="font-mono text-xs text-[var(--ink-primary)] hover:underline inline-flex items-center gap-1"
                                      >
                                        View Case Timeline <IconExternalLink size={10} />
                                      </button>
                                    )}
                                  </div>
                                </div>
                              </div>

                              {/* Evidence Panel */}
                              <EvidencePanel evidence={detail.evidence || []} />
                            </div>
                          ) : (
                            <div className="text-xs text-[var(--ink-secondary)] italic">
                              No additional metadata recorded for this direction.
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </DataTable>
        )}

        {/* Ledger Pagination */}
        {totalPages > 1 && (
          <div className="border border-[var(--border-rule)] bg-[var(--bg-surface)] p-2.5 flex items-center justify-between font-mono text-xs">
            <span className="text-[var(--ink-secondary)] tabular-nums">
              Page {page} of {totalPages} ({total} total records)
            </span>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1 || loading}
                className="px-2.5 py-1 border border-[var(--border-rule-strong)] bg-[var(--bg-paper)] text-[var(--ink-primary)] hover:bg-[var(--bg-surface-muted)] disabled:opacity-40 rounded-[2px] inline-flex items-center gap-1"
              >
                <IconChevronLeft size={12} />
                <span>Previous</span>
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages || loading}
                className="px-2.5 py-1 border border-[var(--border-rule-strong)] bg-[var(--bg-paper)] text-[var(--ink-primary)] hover:bg-[var(--bg-surface-muted)] disabled:opacity-40 rounded-[2px] inline-flex items-center gap-1"
              >
                <span>Next</span>
                <IconChevronRight size={12} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
