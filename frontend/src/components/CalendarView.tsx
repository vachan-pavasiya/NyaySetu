import React, { useState, useEffect } from 'react';
import type { CalendarResponse, CalendarDirectionItem } from '../types';
import { StatusBadge, FlagBadges } from './StatusBadge';
import { PageHeader } from './primitives/PageHeader';
import { DataTable, TableHead, TableRow, TableHeaderCell, TableCell } from './primitives/DataTable';
import { IconChevronLeft, IconChevronRight, IconExternalLink } from './primitives/Icon';
import { getApiUrl } from '../config';

interface CalendarViewProps {
  onSelectJudgment?: (judgmentId: number) => void;
}

export const CalendarView: React.FC<CalendarViewProps> = ({ onSelectJudgment }) => {
  const popularMonths = [
    '2023-10',
    '2023-07',
    '2023-05',
    '2023-08',
    '2023-09',
    '2023-11',
    '2023-12',
    '2024-01',
    '2022-09',
  ];

  const [currentMonth, setCurrentMonth] = useState<string>('2023-10');
  const [data, setData] = useState<CalendarResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchCalendar = async (month: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(getApiUrl(`/calendar?month=${month}`));
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: CalendarResponse = await res.json();
      setData(json);
    } catch (err: any) {
      console.error('Failed to load calendar data:', err);
      setError(err.message || 'Failed to load calendar directions.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCalendar(currentMonth);
  }, [currentMonth]);

  const changeMonth = (delta: number) => {
    const [yearStr, monthStr] = currentMonth.split('-');
    let y = parseInt(yearStr, 10);
    let m = parseInt(monthStr, 10) + delta;
    if (m > 12) {
      m = 1;
      y += 1;
    } else if (m < 1) {
      m = 12;
      y -= 1;
    }
    const newMonth = `${y}-${String(m).padStart(2, '0')}`;
    setCurrentMonth(newMonth);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        volumeOrMeta="Gazette Compliance Schedule"
        title="Compliance Deadline Calendar"
        deck="Deterministic deadline windows grouped by expiration month. All deadlines bound by estimated 30-day service lag."
        actions={
          <div className="flex items-center gap-2">
            <button
              onClick={() => changeMonth(-1)}
              className="p-1.5 border border-[var(--border-rule-strong)] bg-[var(--bg-surface)] hover:bg-[var(--bg-surface-muted)] text-[var(--ink-primary)] rounded-[2px]"
              title="Previous Month"
            >
              <IconChevronLeft size={12} />
            </button>
            <input
              type="month"
              value={currentMonth}
              onChange={(e) => e.target.value && setCurrentMonth(e.target.value)}
              className="px-2 py-1 font-mono text-xs font-semibold border border-[var(--border-rule-strong)] bg-[var(--bg-surface)] text-[var(--ink-primary)] rounded-[2px]"
            />
            <button
              onClick={() => changeMonth(1)}
              className="p-1.5 border border-[var(--border-rule-strong)] bg-[var(--bg-surface)] hover:bg-[var(--bg-surface-muted)] text-[var(--ink-primary)] rounded-[2px]"
              title="Next Month"
            >
              <IconChevronRight size={12} />
            </button>
          </div>
        }
      />

      {/* Quick Jump Bar */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 text-xs font-mono">
        <span className="text-[var(--ink-muted)] shrink-0">Quick jump:</span>
        {popularMonths.map((m) => (
          <button
            key={m}
            onClick={() => setCurrentMonth(m)}
            className={`px-2 py-0.5 border rounded-[2px] transition-colors shrink-0 ${
              currentMonth === m
                ? 'border-[var(--accent-oxblood)] bg-[var(--accent-oxblood)] text-white font-semibold'
                : 'border-[var(--border-rule)] bg-[var(--bg-surface)] text-[var(--ink-secondary)] hover:bg-[var(--bg-surface-muted)]'
            }`}
          >
            {m}
          </button>
        ))}
      </div>

      {/* Summary figures for the month */}
      {data && (
        <div className="border border-[var(--border-rule)] bg-[var(--bg-surface)] p-3 font-mono text-xs flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-6">
            <span>
              Total Due in {currentMonth}: <strong>{data.total_directions}</strong>
            </span>
            <span className="text-[var(--status-complied)]">
              Complied: <strong>{data.status_summary?.COMPLIED || 0}</strong>
            </span>
            <span className="text-[var(--status-pending)]">
              Pending: <strong>{data.status_summary?.PENDING || 0}</strong>
            </span>
            <span className="text-[var(--status-unverified)]">
              Unverified: <strong>{data.status_summary?.UNVERIFIED || 0}</strong>
            </span>
          </div>
          <span className="text-[10px] text-[var(--ink-muted)] uppercase">
            Window bounds: Order date + N + 30 days
          </span>
        </div>
      )}

      {/* Table list */}
      {loading ? (
        <div className="py-20 border border-[var(--border-rule)] bg-[var(--bg-surface)] text-center font-sans text-xs text-[var(--ink-secondary)] italic">
          Loading scheduled directions for {currentMonth}...
        </div>
      ) : error ? (
        <div className="p-4 border border-[var(--status-overdue)] bg-[var(--status-overdue-bg)] text-center font-sans text-xs text-[var(--status-overdue)]">
          {error}
        </div>
      ) : !data || data.directions.length === 0 ? (
        <div className="py-20 border border-[var(--border-rule)] bg-[var(--bg-surface)] text-center font-sans text-xs text-[var(--ink-secondary)] italic">
          No operative mandates with deadline windows closing in {currentMonth}.
        </div>
      ) : (
        <DataTable>
          <TableHead>
            <tr>
              <TableHeaderCell>Window Expiration Date</TableHeaderCell>
              <TableHeaderCell>Responsible Department &amp; Case</TableHeaderCell>
              <TableHeaderCell>Operative Direction Mandate</TableHeaderCell>
              <TableHeaderCell align="center">Compliance Status</TableHeaderCell>
              <TableHeaderCell align="right">Action</TableHeaderCell>
            </tr>
          </TableHead>
          <tbody>
            {data.directions.map((dir: CalendarDirectionItem) => (
              <TableRow key={dir.id}>
                {/* Date */}
                <TableCell>
                  <div className="font-mono font-bold text-xs tabular-nums text-[var(--accent-oxblood)]">
                    {dir.deadline_window_end}
                  </div>
                  <div className="font-mono text-[10px] text-[var(--ink-muted)]">
                    window start: {dir.deadline_window_start}
                  </div>
                </TableCell>

                {/* Responsible authority */}
                <TableCell>
                  <div className="font-serif font-bold text-xs text-[var(--ink-primary)]">
                    {dir.cleaned_department || dir.responsible_party}
                  </div>
                  <div className="font-mono text-[10px] text-[var(--ink-secondary)]">
                    {dir.case_number}
                  </div>
                </TableCell>

                {/* Operative action */}
                <TableCell>
                  <div className="font-sans text-xs text-[var(--ink-primary)] leading-snug">
                    {dir.action}
                  </div>
                  {dir.deadline_phrase && (
                    <div className="font-mono text-[10px] text-[var(--accent-oxblood)] mt-0.5">
                      phrase: &ldquo;{dir.deadline_phrase}&rdquo;
                    </div>
                  )}
                </TableCell>

                {/* Status */}
                <TableCell align="center">
                  <div className="flex flex-col items-center gap-1">
                    <StatusBadge status={dir.compliance_status} size="sm" />
                    {dir.flags && <FlagBadges flags={dir.flags} />}
                  </div>
                </TableCell>

                {/* Action Link */}
                <TableCell align="right">
                  {onSelectJudgment && dir.judgment_id && (
                    <button
                      onClick={() => onSelectJudgment(dir.judgment_id)}
                      className="font-mono text-[11px] text-[var(--accent-oxblood)] hover:underline inline-flex items-center gap-0.5"
                    >
                      Inspect <IconExternalLink size={10} />
                    </button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </tbody>
        </DataTable>
      )}
    </div>
  );
};
