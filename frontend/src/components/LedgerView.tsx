import React, { useState, useEffect } from 'react';
import {
  Download,
  Search,
  ChevronDown,
  ChevronRight,
  AlertCircle,
  RefreshCw,
  ExternalLink,
  ChevronLeft,
  Layers,
  HelpCircle,
} from 'lucide-react';
import type { LedgerItem, LedgerResponse } from '../types';
import { StatusBadge, FlagBadges } from './StatusBadge';
import { EvidencePanel } from './EvidencePanel';
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
  const [pageSize, setPageSize] = useState<number>(20);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [bucketFilter, setBucketFilter] = useState<string>('ALL');
  const [departmentFilter, setDepartmentFilter] = useState<string>(initialDepartment);
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [fromDate, setFromDate] = useState<string>('');
  const [toDate, setToDate] = useState<string>('');
  const [overdueOnly, setOverdueOnly] = useState<boolean>(false);
  const [contemptOnly, setContemptOnly] = useState<boolean>(false);

  // Expanded row ID for evidence panel
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [expandedDetail, setExpandedDetail] = useState<{ [key: number]: any }>({});
  const [loadingDetail, setLoadingDetail] = useState<{ [key: number]: boolean }>({});
  const [showUnverifiedHelp, setShowUnverifiedHelp] = useState<boolean>(false);

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
      setError(err.message || 'Failed to load ledger');
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
    setFromDate('');
    setToDate('');
    setOverdueOnly(false);
    setContemptOnly(false);
    setPage(1);
  };

  const toggleExpand = async (directionId: number) => {
    if (expandedId === directionId) {
      setExpandedId(null);
      return;
    }
    setExpandedId(directionId);

    if (!expandedDetail[directionId]) {
      setLoadingDetail((prev) => ({ ...prev, [directionId]: true }));
      try {
        const res = await fetch(getApiUrl(`/directions/${directionId}`));
        if (res.ok) {
          const detail = await res.json();
          setExpandedDetail((prev) => ({ ...prev, [directionId]: detail }));
        }
      } catch (err) {
        console.error('Failed to load direction detail:', err);
      } finally {
        setLoadingDetail((prev) => ({ ...prev, [directionId]: false }));
      }
    }
  };

  const handleDownloadCsv = () => {
    const params = new URLSearchParams();
    if (statusFilter !== 'ALL') params.append('status', statusFilter);
    if (bucketFilter !== 'ALL') params.append('bucket', bucketFilter);
    if (departmentFilter.trim()) params.append('department', departmentFilter.trim());
    if (searchTerm.trim()) params.append('search', searchTerm.trim());
    if (fromDate) params.append('from', fromDate);
    if (toDate) params.append('to', toDate);
    if (overdueOnly) params.append('overdue_only', 'true');
    if (contemptOnly) params.append('contempt_only', 'true');

    window.location.href = getApiUrl(`/export.csv?${params.toString()}`);
  };

  return (
    <div className="space-y-6">
      {/* Top Controls & Filters */}
      <div className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-xs space-y-4">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-slate-900 tracking-tight">Compliance Ledger</h2>
              <span className="text-2xs font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200">
                {total} Records
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Live ledger of High Court directions with deterministic dates, department cleaning, and verified follow-up findings.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowUnverifiedHelp(!showUnverifiedHelp)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 border border-slate-200 transition-colors"
            >
              <HelpCircle className="w-3.5 h-3.5 text-slate-400" />
              <span>Why UNVERIFIED?</span>
            </button>

            <button
              onClick={handleDownloadCsv}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-white border border-slate-300 text-slate-700 hover:bg-slate-50 shadow-xs transition-all"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Export CSV</span>
            </button>
          </div>
        </div>

        {showUnverifiedHelp && (
          <div className="p-3.5 rounded-lg bg-indigo-50/70 border border-indigo-200 text-xs text-indigo-950 space-y-1">
            <div className="font-bold flex items-center justify-between">
              <span>Why are many directions marked UNVERIFIED?</span>
              <button onClick={() => setShowUnverifiedHelp(false)} className="text-indigo-600 hover:text-indigo-900 font-bold">✕</button>
            </div>
            <p className="text-2xs text-indigo-900/90 leading-relaxed">
              In the Indian High Court system, departments are not required to file compliance certificates back into the original writ case file.
              To avoid false claims, NyaySetu follows the strict rule: <strong>&quot;COMPLIED only when a linked later order has a verified verbatim judicial finding.&quot;</strong>
              Directions without subsequent proceedings stay honestly labeled as <strong>UNVERIFIED</strong> (flagged <code>OVERDUE (NO RECORD)</code> if past deadline).
            </p>
          </div>
        )}

        {/* Filter Inputs Grid */}
        <form onSubmit={handleSearchSubmit} className="space-y-3 pt-2 border-t border-slate-100">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {/* Search Input */}
            <div className="relative">
              <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search action or case..."
                className="w-full pl-9 pr-3 py-1.5 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-1 focus:ring-slate-900 bg-white"
              />
            </div>

            {/* Department Filter */}
            <div className="relative">
              <input
                type="text"
                value={departmentFilter}
                onChange={(e) => setDepartmentFilter(e.target.value)}
                placeholder="Filter by Department..."
                className="w-full px-3 py-1.5 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-1 focus:ring-slate-900 bg-white"
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
                className="w-full px-3 py-1.5 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-1 focus:ring-slate-900 bg-white font-medium"
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
                className="w-full px-3 py-1.5 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-1 focus:ring-slate-900 bg-white font-medium"
              >
                <option value="ALL">All Deadline Buckets</option>
                <option value="LAPSED">Lapsed Window</option>
                <option value="IN_WINDOW">In-Window</option>
                <option value="UPCOMING">Upcoming</option>
                <option value="DEPENDENT">Dependent on Event</option>
                <option value="AMBIGUOUS">Ambiguous Date</option>
                <option value="NO_DEADLINE">No Deadline</option>
              </select>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
            <div className="flex flex-wrap items-center gap-4">
              <label className="flex items-center gap-1.5 text-xs font-medium text-slate-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={overdueOnly}
                  onChange={(e) => {
                    setOverdueOnly(e.target.checked);
                    setPage(1);
                  }}
                  className="rounded border-slate-300 text-rose-600 focus:ring-rose-500"
                />
                <span>Overdue (No Record) only</span>
              </label>

              <label className="flex items-center gap-1.5 text-xs font-medium text-slate-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={contemptOnly}
                  onChange={(e) => {
                    setContemptOnly(e.target.checked);
                    setPage(1);
                  }}
                  className="rounded border-slate-300 text-purple-600 focus:ring-purple-500"
                />
                <span>Contempt Petitions only</span>
              </label>

              {(departmentFilter || searchTerm || statusFilter !== 'ALL' || bucketFilter !== 'ALL' || overdueOnly || contemptOnly) && (
                <button
                  type="button"
                  onClick={handleResetFilters}
                  className="text-xs text-rose-600 hover:text-rose-800 font-semibold underline underline-offset-2"
                >
                  Clear all filters
                </button>
              )}
            </div>

            <button
              type="submit"
              className="px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-slate-900 hover:bg-slate-800 text-white shadow-xs transition-all"
            >
              Apply Search
            </button>
          </div>
        </form>
      </div>

      {/* Ledger Table */}
      <div className="rounded-xl border border-slate-200/80 bg-white shadow-xs overflow-hidden">
        {loading ? (
          <div className="py-24 text-center text-slate-400 text-xs">
            <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2" />
            Loading compliance ledger records...
          </div>
        ) : error ? (
          <div className="py-16 text-center text-rose-600 text-xs">
            <AlertCircle className="w-6 h-6 mx-auto mb-2" />
            {error}
          </div>
        ) : items.length === 0 ? (
          <div className="py-24 text-center text-slate-400 text-xs">
            No compliance directions matched the selected filters.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/75 text-2xs font-semibold uppercase tracking-wider text-slate-500">
                  <th className="py-3 px-4 w-10"></th>
                  <th className="py-3 px-4">Case &amp; Authority</th>
                  <th className="py-3 px-4">Operative Direction</th>
                  <th className="py-3 px-4">Deadline Window</th>
                  <th className="py-3 px-4 text-center">Status &amp; Flags</th>
                  <th className="py-3 px-4 text-center">Evidence</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((item) => {
                  const isExpanded = expandedId === item.id;
                  const detail = expandedDetail[item.id];
                  const isLoadingDet = loadingDetail[item.id];

                  return (
                    <React.Fragment key={item.id}>
                      <tr
                        className={`hover:bg-slate-50/75 transition-colors cursor-pointer ${
                          isExpanded ? 'bg-slate-50/50' : ''
                        }`}
                        onClick={() => toggleExpand(item.id)}
                      >
                        {/* Expand Icon */}
                        <td className="py-3.5 px-4 text-slate-400">
                          {isExpanded ? (
                            <ChevronDown className="w-4 h-4 text-slate-600" />
                          ) : (
                            <ChevronRight className="w-4 h-4" />
                          )}
                        </td>

                        {/* Case & Department */}
                        <td className="py-3.5 px-4 space-y-1">
                          <div className="flex items-center gap-1.5">
                            <span
                              className={`font-mono font-bold text-slate-900 ${
                                onSelectCase && item.case_number ? 'hover:text-blue-600 hover:underline cursor-pointer' : ''
                              }`}
                              onClick={(e) => {
                                if (onSelectCase && item.case_number) {
                                  e.stopPropagation();
                                  onSelectCase(item.case_number);
                                }
                              }}
                              title={onSelectCase ? 'View Case Timeline' : undefined}
                            >
                              {item.case_number || `Judgment #${item.judgment_id}`}
                            </span>
                            {item.judgment_id && onSelectJudgment && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onSelectJudgment(item.judgment_id);
                                }}
                                className="text-slate-400 hover:text-indigo-600"
                                title="Open full judgment view"
                              >
                                <ExternalLink className="w-3 h-3" />
                              </button>
                            )}
                          </div>
                          <div>
                            <div className="font-bold text-slate-800 text-xs" title={`Raw: ${item.responsible_party}`}>
                              {item.cleaned_department || item.responsible_party}
                            </div>
                            {item.cleaned_department && item.cleaned_department !== item.responsible_party && (
                              <div className="text-3xs text-slate-400 line-clamp-1 font-mono">
                                raw: {item.responsible_party}
                              </div>
                            )}
                          </div>
                          {item.judgment_date && (
                            <div className="text-3xs text-slate-400 font-mono">
                              Pronounced: {item.judgment_date}
                            </div>
                          )}
                        </td>

                        {/* Direction Action */}
                        <td className="py-3.5 px-4 max-w-md">
                          <div className="font-medium text-slate-800 line-clamp-2 leading-relaxed">
                            {item.action}
                          </div>
                          {item.deadline_phrase && (
                            <div className="text-3xs text-slate-500 font-mono mt-1">
                              Ordered phrase: &quot;{item.deadline_phrase}&quot;
                            </div>
                          )}
                        </td>

                        {/* Deadline Window */}
                        <td className="py-3.5 px-4 space-y-1 font-mono text-2xs">
                          {item.deadline_window_start && item.deadline_window_end ? (
                            <div>
                              <div className="text-slate-900 font-semibold">
                                {item.deadline_window_start} &rarr; {item.deadline_window_end}
                              </div>
                              <div className="text-3xs text-slate-400 font-sans">
                                {item.deadline_status === 'LAPSED' ? (
                                  <span className="text-rose-600 font-medium">Window lapsed</span>
                                ) : (
                                  <span>Active window</span>
                                )}
                              </div>
                            </div>
                          ) : (
                            <span className="text-slate-400 italic">No window computed</span>
                          )}
                          {item.explanation_text && (
                            <div className="text-3xs text-slate-400 font-sans line-clamp-1">
                              {item.explanation_text}
                            </div>
                          )}
                        </td>

                        {/* Status & Flags */}
                        <td className="py-3.5 px-4 text-center space-y-1.5">
                          <StatusBadge status={item.compliance_status || item.status} />
                          <FlagBadges flags={item.flags} />
                          {item.sub_reason && (
                            <div className="text-3xs text-slate-400 max-w-xs mx-auto line-clamp-1">
                              {item.sub_reason}
                            </div>
                          )}
                        </td>

                        {/* Evidence Badge */}
                        <td className="py-3.5 px-4 text-center space-y-1">
                          {item.evidence_strength ? (
                            <span
                              className={`inline-block px-2 py-0.5 rounded-full text-3xs font-semibold ${
                                item.evidence_strength === 'COURT_RECORDED'
                                  ? 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                                  : 'bg-indigo-100 text-indigo-800 border border-indigo-200'
                              }`}
                            >
                              {item.evidence_strength === 'COURT_RECORDED' ? 'Court Recorded' : 'Party Submission'}
                            </span>
                          ) : (
                            <span className="text-slate-400 text-3xs font-mono">None</span>
                          )}

                          {item.evidence_scope === 'CASE_LEVEL' && (
                            <div className="flex items-center justify-center gap-1 text-3xs text-indigo-700 font-medium">
                              <Layers className="w-2.5 h-2.5" />
                              <span>Case-level ({item.directions_covered_count || 1} dirs)</span>
                            </div>
                          )}
                        </td>
                      </tr>

                      {/* Expandable Evidence & Quote Panel */}
                      {isExpanded && (
                        <tr className="bg-slate-50/75 border-b border-slate-200">
                          <td colSpan={6} className="p-4 pl-12 space-y-4">
                            {isLoadingDet ? (
                              <div className="py-4 text-center text-slate-400 text-xs">
                                <RefreshCw className="w-4 h-4 animate-spin mx-auto mb-1" />
                                Loading evidence records...
                              </div>
                            ) : detail ? (
                              <div className="space-y-4">
                                {/* Case level note */}
                                {detail.evidence_scope === 'CASE_LEVEL' && (
                                  <div className="p-2.5 rounded-lg bg-indigo-50 border border-indigo-200 text-xs text-indigo-900">
                                    <strong>Case-level Evidence:</strong> This follow-up order covers {detail.directions_covered_count || 'multiple'} directions across the matter. It records overarching compliance for the case rather than individual direction proof.
                                  </div>
                                )}

                                {/* Source Quote */}
                                <div className="space-y-1">
                                  <div className="text-3xs font-bold uppercase tracking-wider text-slate-400">
                                    Original Operative Quote (Verbatim from Order)
                                  </div>
                                  <blockquote className="p-3 bg-white border-l-3 border-slate-900 rounded-r text-xs text-slate-800 font-serif leading-relaxed shadow-2xs">
                                    &quot;{detail.source_quote}&quot;
                                  </blockquote>
                                </div>

                                {/* Full Evidence Panel */}
                                <EvidencePanel evidence={detail.evidence || []} />
                              </div>
                            ) : (
                              <div className="text-2xs text-slate-400">No additional details available.</div>
                            )}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Footer */}
        <div className="p-4 border-t border-slate-200 bg-slate-50/75 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-600">
          <div className="flex items-center gap-2">
            <span>Showing page <strong>{page}</strong> of <strong>{totalPages}</strong> ({total} total directions)</span>
            <span className="text-slate-300">|</span>
            <span>Per page:</span>
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setPage(1);
              }}
              className="px-2 py-0.5 text-xs rounded border border-slate-200 bg-white font-medium"
            >
              <option value="10">10</option>
              <option value="20">20</option>
              <option value="50">50</option>
              <option value="100">100</option>
            </select>
          </div>

          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setPage(Math.max(1, page - 1))}
              disabled={page <= 1}
              className="flex items-center gap-1 px-3 py-1 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed font-medium shadow-2xs transition-colors"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
              <span>Previous</span>
            </button>
            <button
              onClick={() => setPage(Math.min(totalPages, page + 1))}
              disabled={page >= totalPages}
              className="flex items-center gap-1 px-3 py-1 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed font-medium shadow-2xs transition-colors"
            >
              <span>Next</span>
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
