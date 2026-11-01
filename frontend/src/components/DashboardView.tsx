import React, { useState, useEffect } from 'react';
import type { DashboardResponse } from '../types';
import { AgentActivityFeed } from './AgentActivityFeed';
import { getApiUrl } from '../config';
import { PageHeader } from './primitives/PageHeader';
import { MetricFigure, MetricFigureRow } from './primitives/Figure';
import { DataTable, TableHead, TableRow, TableHeaderCell, TableCell } from './primitives/DataTable';
import { Stamp } from './primitives/Stamp';
import { IconRefresh, IconExternalLink } from './primitives/Icon';

interface DashboardViewProps {
  onSelectDepartment: (department: string) => void;
  onSelectJudgment: (judgmentId: number) => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  onSelectDepartment,
  onSelectJudgment,
}) => {
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [showUnverifiedNote, setShowUnverifiedNote] = useState<boolean>(false);

  const fetchDashboard = async () => {
    setLoading(true);
    try {
      const res = await fetch(getApiUrl('/dashboard'));
      if (res.ok) {
        const json = await res.json();
        setData(json);
      }
    } catch (err) {
      console.error('Failed to fetch dashboard data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboard();
  }, []);

  if (loading) {
    return (
      <div className="py-20 border border-[var(--border-rule)] bg-[var(--bg-surface)] text-center font-sans text-xs text-[var(--ink-secondary)] italic">
        Loading compliance register telemetry from database...
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-6 border border-[var(--status-overdue)] bg-[var(--status-overdue-bg)] text-center font-sans text-xs text-[var(--status-overdue)]">
        Unable to retrieve register data. Please verify the backend server is reachable.
      </div>
    );
  }

  const totalDirs =
    (data.status_counts.COMPLIED || 0) +
    (data.status_counts.PENDING || 0) +
    (data.status_counts.UNVERIFIED || 0);

  const compliedPct = totalDirs > 0 ? (((data.status_counts.COMPLIED || 0) / totalDirs) * 100).toFixed(1) : '0';
  const pendingPct = totalDirs > 0 ? (((data.status_counts.PENDING || 0) / totalDirs) * 100).toFixed(1) : '0';
  const unverifiedPct = totalDirs > 0 ? (((data.status_counts.UNVERIFIED || 0) / totalDirs) * 100).toFixed(1) : '0';

  return (
    <div className="space-y-6">
      {/* Editorial Page Header */}
      <PageHeader
        volumeOrMeta="Calcutta High Court (Appellate Side) · Public Register"
        title="Court-Order Compliance Radar"
        deck="Operative judicial directions extracted from official open judgments. Compliance requires a verified verbatim quote from a linked subsequent order."
        actions={
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowUnverifiedNote(!showUnverifiedNote)}
              className="font-mono text-xs text-[var(--accent-oxblood)] hover:underline px-2 py-1"
            >
              Why UNVERIFIED?
            </button>
            <button
              onClick={fetchDashboard}
              className="font-mono text-xs uppercase tracking-wider font-semibold px-3 py-1.5 border border-[var(--border-rule-strong)] bg-[var(--bg-surface)] hover:bg-[var(--bg-surface-muted)] text-[var(--ink-primary)] rounded-[2px] inline-flex items-center gap-1.5"
            >
              <IconRefresh size={12} className={loading ? 'animate-spin' : ''} />
              <span>Refresh</span>
            </button>
          </div>
        }
      />

      {/* Gazette Ground-Truth Clarification */}
      {showUnverifiedNote && (
        <div className="border border-[var(--border-rule-strong)] bg-[var(--bg-surface)] p-4 font-sans text-xs text-[var(--ink-primary)] space-y-2">
          <div className="flex items-center justify-between border-b border-[var(--border-rule)] pb-1.5">
            <span className="font-serif font-bold text-sm">
              The Three-Status Ground-Truth Standard
            </span>
            <button
              onClick={() => setShowUnverifiedNote(false)}
              className="font-mono text-xs text-[var(--ink-muted)] hover:text-[var(--ink-primary)] font-bold"
            >
              [Close]
            </button>
          </div>
          <p className="text-[var(--ink-secondary)] leading-relaxed">
            High Court judgments do not automatically report administrative compliance back to the original case file. Under our scoring guardrails, <strong>NyaySetu never infers compliance from silence</strong>.
          </p>
          <ul className="list-disc pl-5 space-y-1 font-sans text-xs text-[var(--ink-secondary)]">
            <li>
              <strong>COMPLIED:</strong> Verified only when a linked later order contains an exact verbatim finding confirming execution.
            </li>
            <li>
              <strong>PENDING:</strong> The deadline window is open, or a later order shows an ongoing process (extension sought, compliance report awaited).
            </li>
            <li>
              <strong>UNVERIFIED:</strong> No public subsequent order was found either way. It does not mean the order was ignored.
            </li>
          </ul>
        </div>
      )}

      {/* Large Serif Metric Figures Row */}
      <MetricFigureRow>
        <MetricFigure
          value={data.status_counts.COMPLIED || 0}
          label="COMPLIED"
          sublabel={`${compliedPct}% verified in later orders`}
          statusVariant="complied"
        />
        <MetricFigure
          value={data.status_counts.PENDING || 0}
          label="PENDING"
          sublabel={`${pendingPct}% ongoing or window open`}
          statusVariant="pending"
        />
        <MetricFigure
          value={data.status_counts.UNVERIFIED || 0}
          label="UNVERIFIED"
          sublabel={`${unverifiedPct}% no public record found`}
          statusVariant="unverified"
        />
        <MetricFigure
          value={data.overdue_no_record_count || 0}
          label="OVERDUE (NO RECORD)"
          sublabel="Window lapsed without order"
          statusVariant="oxblood"
        />
        <MetricFigure
          value={data.contempt_filed_count || 0}
          label="CONTEMPT PETITIONS"
          sublabel="Alleging non-compliance"
          statusVariant="oxblood"
        />
        <MetricFigure
          value={totalDirs}
          label="TOTAL DIRECTIONS"
          sublabel={`In ${data.dataset_freshness.analysed_count} judgments`}
          statusVariant="neutral"
        />
      </MetricFigureRow>

      {/* Flat Status Distribution Bar (Ledger Style) */}
      <div className="border border-[var(--border-rule)] bg-[var(--bg-surface)] p-3 space-y-2">
        <div className="flex items-baseline justify-between font-mono text-xs">
          <span className="font-semibold uppercase tracking-wider text-[var(--ink-secondary)]">
            Distribution of Operative Mandates
          </span>
          <span className="text-[var(--ink-muted)] tabular-nums">
            {totalDirs} Total Tracked Directions
          </span>
        </div>

        {/* Flat ruled bar without color blends or pill shapes */}
        <div className="h-3 w-full border border-[var(--border-rule-strong)] bg-[var(--bg-surface-muted)] flex">
          <div
            style={{ width: `${compliedPct}%` }}
            className="h-full bg-[var(--status-complied)]"
            title={`COMPLIED: ${data.status_counts.COMPLIED || 0} (${compliedPct}%)`}
          />
          <div
            style={{ width: `${pendingPct}%` }}
            className="h-full bg-[var(--status-pending)]"
            title={`PENDING: ${data.status_counts.PENDING || 0} (${pendingPct}%)`}
          />
          <div
            style={{ width: `${unverifiedPct}%` }}
            className="h-full bg-[var(--status-unverified)]"
            title={`UNVERIFIED: ${data.status_counts.UNVERIFIED || 0} (${unverifiedPct}%)`}
          />
        </div>

        <div className="flex items-center justify-between font-mono text-[11px] text-[var(--ink-secondary)] pt-0.5">
          <span>Complied: {data.status_counts.COMPLIED || 0} ({compliedPct}%)</span>
          <span>Pending: {data.status_counts.PENDING || 0} ({pendingPct}%)</span>
          <span>Unverified: {data.status_counts.UNVERIFIED || 0} ({unverifiedPct}%)</span>
        </div>
      </div>

      {/* Core Editorial Tables: Orders Against Departments & Upcoming Deadlines */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Department Leaderboard (2 cols) */}
        <div className="lg:col-span-2 space-y-2">
          <div className="flex items-baseline justify-between">
            <h2 className="font-serif font-bold text-base text-[var(--ink-primary)]">
              Orders against government departments
            </h2>
            <span className="font-mono text-[10px] text-[var(--ink-muted)] uppercase">
              Click row to filter ledger
            </span>
          </div>

          <DataTable>
            <TableHead>
              <tr>
                <TableHeaderCell>Responsible Department</TableHeaderCell>
                <TableHeaderCell align="right">Total</TableHeaderCell>
                <TableHeaderCell align="right">Complied</TableHeaderCell>
                <TableHeaderCell align="right">Pending</TableHeaderCell>
                <TableHeaderCell align="right">Unverified</TableHeaderCell>
              </tr>
            </TableHead>
            <tbody>
              {data.top_departments.length === 0 ? (
                <TableRow>
                  <TableCell className="text-center italic" align="center">
                    No department directions recorded yet.
                  </TableCell>
                </TableRow>
              ) : (
                data.top_departments.map((dept, idx) => (
                  <TableRow
                    key={idx}
                    isClickable
                    onClick={() => onSelectDepartment(dept.department)}
                  >
                    <TableCell>
                      <div className="font-serif font-bold text-sm text-[var(--ink-primary)] hover:text-[var(--accent-oxblood)]">
                        {dept.department}
                      </div>
                      <div className="font-mono text-[10px] text-[var(--ink-muted)]">
                        {dept.total} total directions
                      </div>
                    </TableCell>
                    <TableCell align="right" className="font-mono tabular-nums font-bold">
                      {dept.total}
                    </TableCell>
                    <TableCell align="right" className="font-mono tabular-nums text-[var(--status-complied)] font-semibold">
                      {dept.complied || 0}
                    </TableCell>
                    <TableCell align="right" className="font-mono tabular-nums text-[var(--status-pending)] font-semibold">
                      {dept.pending || 0}
                    </TableCell>
                    <TableCell align="right" className="font-mono tabular-nums text-[var(--status-unverified)] font-semibold">
                      {dept.unverified || 0}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </tbody>
          </DataTable>
        </div>

        {/* Mandates Due Soon (1 col) */}
        <div className="space-y-2">
          <div className="flex items-baseline justify-between">
            <h2 className="font-serif font-bold text-base text-[var(--ink-primary)]">
              Directions due in next 30 days
            </h2>
            <span className="font-mono text-[10px] text-[var(--ink-muted)] uppercase">
              {data.directions_due_next_30_days.length} orders
            </span>
          </div>

          <div className="border border-[var(--border-rule)] bg-[var(--bg-surface)] divide-y divide-[var(--border-rule)] max-h-[380px] overflow-y-auto">
            {data.directions_due_next_30_days.length === 0 ? (
              <div className="p-6 text-center font-sans text-xs text-[var(--ink-secondary)] italic">
                No operative directions with deadline windows closing in the next 30 days.
              </div>
            ) : (
              data.directions_due_next_30_days.map((dir) => (
                <div
                  key={dir.id}
                  onClick={() => onSelectJudgment(dir.judgment_id)}
                  className="p-3 hover:bg-[var(--bg-surface-muted)] cursor-pointer transition-colors space-y-1"
                >
                  <div className="flex items-center justify-between gap-2">
                    <Stamp status={dir.compliance_status} size="sm" />
                    {dir.deadline_window_end && (
                      <span className="font-mono text-[11px] text-[var(--accent-oxblood)] font-bold tabular-nums">
                        Due {dir.deadline_window_end}
                      </span>
                    )}
                  </div>
                  <div className="font-serif font-bold text-xs text-[var(--ink-primary)] line-clamp-1">
                    {dir.responsible_party}
                  </div>
                  <div className="font-sans text-xs text-[var(--ink-secondary)] line-clamp-2 leading-tight">
                    {dir.action}
                  </div>
                  <div className="font-mono text-[10px] text-[var(--ink-muted)] pt-0.5 flex items-center justify-between">
                    <span>{dir.case_number}</span>
                    <span className="text-[var(--accent-oxblood)] inline-flex items-center gap-0.5">
                      Inspect <IconExternalLink size={10} />
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Dataset Provenance & Freshness Bar */}
      <div className="border border-[var(--border-rule)] bg-[var(--bg-surface)] p-3 font-mono text-xs">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-center divide-x divide-[var(--border-rule)]">
          <div className="px-2">
            <div className="text-[10px] uppercase text-[var(--ink-muted)]">Ingested Judgments</div>
            <div className="text-base font-bold tabular-nums text-[var(--ink-primary)]">
              {data.dataset_freshness.total_judgments}
            </div>
          </div>
          <div className="px-2">
            <div className="text-[10px] uppercase text-[var(--ink-muted)]">Analysed Judgments</div>
            <div className="text-base font-bold tabular-nums text-[var(--ink-primary)]">
              {data.dataset_freshness.analysed_count}
            </div>
          </div>
          <div className="px-2">
            <div className="text-[10px] uppercase text-[var(--ink-muted)]">Cross-Order Links</div>
            <div className="text-base font-bold tabular-nums text-[var(--ink-primary)]">
              {data.link_stats.total_links}
            </div>
          </div>
          <div className="px-2">
            <div className="text-[10px] uppercase text-[var(--ink-muted)]">Latest Judgment Date</div>
            <div className="text-base font-bold tabular-nums text-[var(--ink-primary)]">
              {data.dataset_freshness.latest_judgment_date || 'N/A'}
            </div>
          </div>
        </div>
      </div>

      {/* Follow-Up Pipeline Activity Feed */}
      <AgentActivityFeed />
    </div>
  );
};
