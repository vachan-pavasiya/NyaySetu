import React, { useState, useEffect } from 'react';
import {
  CheckCircle2,
  Clock,
  HelpCircle,
  AlertTriangle,
  ShieldAlert,
  Scale,
  RefreshCw,
  Database,
  Calendar,
  ChevronRight,
  ExternalLink,
  Info,
} from 'lucide-react';
import type { DashboardResponse } from '../types';
import { AgentActivityFeed } from './AgentActivityFeed';
import { getApiUrl } from '../config';

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
  const [showUnverifiedTooltip, setShowUnverifiedTooltip] = useState<boolean>(false);

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
      <div className="rounded-xl border border-slate-200 bg-white py-24 text-center text-slate-400 text-xs">
        <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-600" />
        Loading Compliance Radar dashboard telemetry...
      </div>
    );
  }

  if (!data) {
    return (
      <div className="rounded-xl border border-rose-200 bg-rose-50 p-6 text-center text-rose-800 text-xs">
        Failed to load dashboard telemetry. Please ensure the backend server is running.
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
      {/* Prominent Legal Tech Notice */}
      <div className="rounded-xl border border-indigo-200 bg-indigo-50/60 p-4 shadow-2xs flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-indigo-600 text-white shrink-0">
            <Info className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-indigo-950 uppercase tracking-wide">
                Strict Compliance Verification Architecture
              </span>
              <span className="text-3xs font-semibold px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-800 border border-indigo-200">
                Official Open Data
              </span>
            </div>
            <p className="text-xs text-indigo-900 font-medium mt-0.5">
              &quot;{data.unverified_note}&quot; Under zero-hallucination guardrails, compliance is never assumed without a verbatim judicial finding in subsequent proceedings.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => setShowUnverifiedTooltip(!showUnverifiedTooltip)}
            className="text-2xs font-semibold text-indigo-700 hover:text-indigo-900 underline underline-offset-2"
          >
            Why UNVERIFIED?
          </button>
          <button
            onClick={fetchDashboard}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white border border-indigo-200 text-indigo-800 hover:bg-indigo-50 shadow-2xs transition-all"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Explanatory Modal / Tooltip */}
      {showUnverifiedTooltip && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm text-xs text-slate-700 space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-bold text-slate-900">The 3-Status Ground-Truth Compliance Model</span>
            <button
              onClick={() => setShowUnverifiedTooltip(false)}
              className="text-slate-400 hover:text-slate-600 text-xs font-bold"
            >
              ✕
            </button>
          </div>
          <p className="text-2xs text-slate-600 leading-relaxed">
            Indian High Court orders do not report compliance back into the original writ docket automatically.
            Therefore, compliance is marked <strong>COMPLIED</strong> only when a linked later order (e.g. contempt petition, compliance affidavit) contains a verified verbatim judicial finding.
            If the deadline window is active or ongoing steps are directed, it is marked <strong>PENDING</strong>.
            If no later order has been ingested or linked yet, it is marked <strong>UNVERIFIED</strong> (with an <code>overdue_no_record</code> flag if the deadline lapsed).
          </p>
        </div>
      )}

      {/* Dataset Freshness & Scope Bar */}
      <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2 text-slate-600">
            <Database className="w-4 h-4 text-indigo-500" />
            <span className="text-2xs text-slate-500">Live Ingested Judgments:</span>
            <span className="text-xs font-bold text-slate-900 font-mono">
              {data.dataset_freshness.total_judgments}
            </span>
          </div>

          <div className="flex items-center gap-2 text-slate-600">
            <Scale className="w-4 h-4 text-emerald-500" />
            <span className="text-2xs text-slate-500">Operative Directions:</span>
            <span className="text-xs font-bold text-slate-900 font-mono">{totalDirs}</span>
          </div>

          <div className="flex items-center gap-2 text-slate-600">
            <Calendar className="w-4 h-4 text-amber-500" />
            <span className="text-2xs text-slate-500">Latest Judgment Date:</span>
            <span className="text-xs font-bold text-slate-900 font-mono">
              {data.dataset_freshness.latest_judgment_date || 'N/A'}
            </span>
          </div>
        </div>

        <div className="text-3xs text-slate-400 font-mono uppercase tracking-wider">
          Source: AWS Open Data (indian-high-court-judgments)
        </div>
      </div>

      {/* Top Headline Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Directions */}
        <div className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-2xs space-y-1">
          <div className="text-2xs font-semibold uppercase tracking-wider text-slate-400">Total Directions</div>
          <div className="text-3xl font-extrabold text-slate-900 font-mono">{totalDirs}</div>
          <div className="text-2xs text-slate-500">Across {data.dataset_freshness.analysed_count} analyzed judgments</div>
        </div>

        {/* Complied */}
        <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-5 shadow-2xs space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-2xs font-bold uppercase tracking-wider text-emerald-800">COMPLIED</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
          </div>
          <div className="text-3xl font-extrabold text-emerald-700 font-mono">{data.status_counts.COMPLIED || 0}</div>
          <div className="text-2xs text-emerald-800/80">{compliedPct}% verified in later orders</div>
        </div>

        {/* Pending */}
        <div className="rounded-xl border border-amber-200 bg-amber-50/50 p-5 shadow-2xs space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-2xs font-bold uppercase tracking-wider text-amber-800">PENDING</span>
            <Clock className="w-4 h-4 text-amber-600" />
          </div>
          <div className="text-3xl font-extrabold text-amber-700 font-mono">{data.status_counts.PENDING || 0}</div>
          <div className="text-2xs text-amber-800/80">{pendingPct}% ongoing process / in-window</div>
        </div>

        {/* Unverified */}
        <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-5 shadow-2xs space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-2xs font-bold uppercase tracking-wider text-slate-700">UNVERIFIED</span>
            <HelpCircle className="w-4 h-4 text-slate-500" />
          </div>
          <div className="text-3xl font-extrabold text-slate-700 font-mono">{data.status_counts.UNVERIFIED || 0}</div>
          <div className="text-2xs text-slate-500">{unverifiedPct}% no subsequent evidence found</div>
        </div>
      </div>

      {/* Visual Status Breakdown Distribution Bar */}
      <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs space-y-2">
        <div className="flex items-center justify-between text-xs font-semibold text-slate-700">
          <span>Compliance Radar Status Distribution</span>
          <span className="text-2xs text-slate-400 font-mono">{totalDirs} Directions Tracked</span>
        </div>
        <div className="h-3.5 w-full bg-slate-100 rounded-full overflow-hidden flex">
          <div
            style={{ width: `${compliedPct}%` }}
            className="bg-emerald-600 h-full transition-all duration-500"
            title={`COMPLIED: ${data.status_counts.COMPLIED || 0} (${compliedPct}%)`}
          />
          <div
            style={{ width: `${pendingPct}%` }}
            className="bg-amber-500 h-full transition-all duration-500"
            title={`PENDING: ${data.status_counts.PENDING || 0} (${pendingPct}%)`}
          />
          <div
            style={{ width: `${unverifiedPct}%` }}
            className="bg-slate-400 h-full transition-all duration-500"
            title={`UNVERIFIED: ${data.status_counts.UNVERIFIED || 0} (${unverifiedPct}%)`}
          />
        </div>
        <div className="flex items-center justify-between text-2xs font-medium text-slate-500 pt-1">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-600 inline-block" />
            <span>Complied: {compliedPct}%</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block" />
            <span>Pending: {pendingPct}%</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-slate-400 inline-block" />
            <span>Unverified: {unverifiedPct}%</span>
          </div>
        </div>
      </div>

      {/* Secondary Guardrail Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Overdue */}
        <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-4 shadow-2xs flex items-center justify-between">
          <div>
            <div className="text-2xs font-semibold uppercase tracking-wider text-rose-700">Overdue (No Record)</div>
            <div className="text-2xl font-extrabold text-rose-800 font-mono mt-0.5">{data.overdue_no_record_count}</div>
            <div className="text-3xs text-rose-600/80">Lapsed without evidence</div>
          </div>
          <AlertTriangle className="w-6 h-6 text-rose-500/80" />
        </div>

        {/* Contempt Filed */}
        <div className="rounded-xl border border-purple-200 bg-purple-50/50 p-4 shadow-2xs flex items-center justify-between">
          <div>
            <div className="text-2xs font-semibold uppercase tracking-wider text-purple-700">Contempt Petitions</div>
            <div className="text-2xl font-extrabold text-purple-800 font-mono mt-0.5">{data.contempt_filed_count}</div>
            <div className="text-3xs text-purple-600/80">Alleging non-compliance</div>
          </div>
          <ShieldAlert className="w-6 h-6 text-purple-500/80" />
        </div>

        {/* Evidence Strength */}
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xs flex items-center justify-between">
          <div>
            <div className="text-2xs font-semibold uppercase tracking-wider text-slate-500">Evidence Strength</div>
            <div className="text-xs font-medium text-slate-800 mt-1">
              <span className="font-bold text-emerald-700">{data.evidence_strength_split?.COURT_RECORDED || 0}</span> Court Recorded <br />
              <span className="font-bold text-indigo-700">{data.evidence_strength_split?.PARTY_SUBMISSION || 0}</span> Party Submission
            </div>
          </div>
          <Scale className="w-6 h-6 text-slate-400" />
        </div>

        {/* Total Links */}
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xs flex items-center justify-between">
          <div>
            <div className="text-2xs font-semibold uppercase tracking-wider text-slate-500">Linked Proceedings</div>
            <div className="text-2xl font-extrabold text-slate-800 font-mono mt-0.5">{data.link_stats.total_links}</div>
            <div className="text-3xs text-slate-400">Contempt &amp; citations mapped</div>
          </div>
          <ExternalLink className="w-6 h-6 text-slate-400" />
        </div>
      </div>

      {/* Department Leaderboard & Upcoming Deadlines Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Department Leaderboard (2 cols) */}
        <div className="lg:col-span-2 rounded-xl border border-slate-200/80 bg-white shadow-2xs overflow-hidden flex flex-col">
          <div className="p-4 border-b border-slate-100 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-slate-900">Department Compliance Leaderboard</h3>
              <p className="text-2xs text-slate-500">
                Top 10 departments ranked by open compliance burden (Click any department to filter the Ledger)
              </p>
            </div>
            <span className="text-3xs font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
              Interactive
            </span>
          </div>

          <div className="overflow-x-auto flex-1">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/75 text-2xs font-semibold uppercase tracking-wider text-slate-500">
                  <th className="py-2.5 px-4">Department / Authority</th>
                  <th className="py-2.5 px-3 text-center text-rose-700">Open</th>
                  <th className="py-2.5 px-3 text-center text-emerald-700">Complied</th>
                  <th className="py-2.5 px-3 text-center text-amber-700">Pending</th>
                  <th className="py-2.5 px-3 text-center text-slate-600">Unverified</th>
                  <th className="py-2.5 px-4 text-center">Total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.top_departments.map((d, idx) => (
                  <tr
                    key={idx}
                    onClick={() => onSelectDepartment(d.department)}
                    className="hover:bg-indigo-50/50 cursor-pointer transition-colors group"
                  >
                    <td className="py-2.5 px-4 font-semibold text-slate-900 group-hover:text-indigo-600 flex items-center justify-between">
                      <span className="line-clamp-1">{d.department}</span>
                      <ChevronRight className="w-3.5 h-3.5 text-slate-300 group-hover:text-indigo-500 shrink-0 ml-1" />
                    </td>
                    <td className="py-2.5 px-3 text-center font-mono font-bold text-rose-700">{d.open_count}</td>
                    <td className="py-2.5 px-3 text-center font-mono text-emerald-700 font-semibold">{d.complied}</td>
                    <td className="py-2.5 px-3 text-center font-mono text-amber-700 font-semibold">{d.pending}</td>
                    <td className="py-2.5 px-3 text-center font-mono text-slate-600">{d.unverified}</td>
                    <td className="py-2.5 px-4 text-center font-mono font-bold text-slate-900">{d.total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Upcoming Deadlines (1 col) */}
        <div className="rounded-xl border border-slate-200/80 bg-white shadow-2xs overflow-hidden flex flex-col">
          <div className="p-4 border-b border-slate-100">
            <h3 className="text-sm font-bold text-slate-900">Upcoming Deadlines</h3>
            <p className="text-2xs text-slate-500">Directions with active or upcoming compliance windows</p>
          </div>

          <div className="p-4 flex-1 overflow-y-auto max-h-96 space-y-3">
            {data.directions_due_next_30_days.length === 0 ? (
              <div className="py-12 text-center text-xs text-slate-400">
                <Clock className="w-5 h-5 mx-auto mb-1 text-slate-300" />
                No directions currently due in the next 30 days.
              </div>
            ) : (
              data.directions_due_next_30_days.map((dir) => (
                <div
                  key={dir.id}
                  onClick={() => onSelectJudgment(dir.judgment_id)}
                  className="p-3 rounded-lg border border-slate-200 hover:border-indigo-300 bg-slate-50/50 hover:bg-indigo-50/30 transition-all cursor-pointer space-y-1.5"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-2xs font-bold text-slate-900 font-mono">{dir.case_number || `Judgment #${dir.judgment_id}`}</span>
                    <span className="text-3xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 border border-amber-200">
                      Due: {dir.deadline_window_end}
                    </span>
                  </div>
                  <div className="text-xs font-medium text-slate-800 line-clamp-1">{dir.cleaned_department}</div>
                  <div className="text-2xs text-slate-500 line-clamp-2">{dir.action}</div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Autonomous Follow-Up Activity Feed */}
      <AgentActivityFeed />
    </div>
  );
};

