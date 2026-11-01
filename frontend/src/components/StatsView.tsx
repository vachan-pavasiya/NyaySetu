import React, { useState, useEffect } from 'react';
import { CheckCircle2, Clock, HelpCircle, AlertTriangle, ShieldAlert, Scale, Layers, RefreshCw } from 'lucide-react';
import type { OverallStats } from '../types';
import { AgentActivityFeed } from './AgentActivityFeed';

export const StatsView: React.FC = () => {
  const [stats, setStats] = useState<OverallStats | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const fetchStats = async () => {
    setLoading(true);
    try {
      let res = await fetch('/api/stats');
      if (!res.ok) {
        res = await fetch('http://127.0.0.1:8000/stats');
      }
      if (res.ok) {
        const data = await res.json();
        setStats(data);
      }
    } catch (err) {
      console.error('Failed to fetch stats:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
  }, []);

  if (loading) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white py-24 text-center text-slate-400 text-xs">
        <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2" />
        Loading compliance statistics...
      </div>
    );
  }

  if (!stats) return null;

  const compliedPct = stats.total_directions > 0 ? ((stats.status_distribution.COMPLIED / stats.total_directions) * 100).toFixed(1) : '0';
  const pendingPct = stats.total_directions > 0 ? ((stats.status_distribution.PENDING / stats.total_directions) * 100).toFixed(1) : '0';
  const unverifiedPct = stats.total_directions > 0 ? ((stats.status_distribution.UNVERIFIED / stats.total_directions) * 100).toFixed(1) : '0';

  return (
    <div className="space-y-6">
      {/* Top Headline Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Directions */}
        <div className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-xs space-y-1">
          <div className="text-2xs font-semibold uppercase tracking-wider text-slate-400">Total Directions</div>
          <div className="text-2xl font-bold text-slate-900 font-mono">{stats.total_directions}</div>
          <div className="text-2xs text-slate-500">Across {stats.total_judgments} ingested judgments</div>
        </div>

        {/* Complied */}
        <div className="rounded-xl border border-emerald-200/80 bg-emerald-50/40 p-5 shadow-xs space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-2xs font-semibold uppercase tracking-wider text-emerald-800">COMPLIED</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
          </div>
          <div className="text-2xl font-bold text-emerald-700 font-mono">{stats.status_distribution.COMPLIED}</div>
          <div className="text-2xs text-emerald-800/80">{compliedPct}% verified in follow-up orders</div>
        </div>

        {/* Pending */}
        <div className="rounded-xl border border-amber-200/80 bg-amber-50/40 p-5 shadow-xs space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-2xs font-semibold uppercase tracking-wider text-amber-800">PENDING</span>
            <Clock className="w-4 h-4 text-amber-600" />
          </div>
          <div className="text-2xl font-bold text-amber-700 font-mono">{stats.status_distribution.PENDING}</div>
          <div className="text-2xs text-amber-800/80">{pendingPct}% ongoing process / in-window</div>
        </div>

        {/* Unverified */}
        <div className="rounded-xl border border-slate-200/80 bg-slate-50/50 p-5 shadow-xs space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-2xs font-semibold uppercase tracking-wider text-slate-600">UNVERIFIED</span>
            <HelpCircle className="w-4 h-4 text-slate-500" />
          </div>
          <div className="text-2xl font-bold text-slate-700 font-mono">{stats.status_distribution.UNVERIFIED}</div>
          <div className="text-2xs text-slate-500">{unverifiedPct}% no subsequent evidence</div>
        </div>
      </div>

      {/* Secondary Guardrail Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Overdue */}
        <div className="rounded-xl border border-rose-200/80 bg-rose-50/40 p-4 shadow-xs flex items-center justify-between">
          <div>
            <div className="text-2xs font-semibold uppercase tracking-wider text-rose-700">Overdue (No Record)</div>
            <div className="text-xl font-bold text-rose-800 font-mono mt-0.5">{stats.flags_distribution.overdue_no_record}</div>
          </div>
          <AlertTriangle className="w-6 h-6 text-rose-500/80" />
        </div>

        {/* Contempt Filed */}
        <div className="rounded-xl border border-purple-200/80 bg-purple-50/40 p-4 shadow-xs flex items-center justify-between">
          <div>
            <div className="text-2xs font-semibold uppercase tracking-wider text-purple-700">Contempt Petitions</div>
            <div className="text-xl font-bold text-purple-800 font-mono mt-0.5">{stats.flags_distribution.contempt_filed}</div>
          </div>
          <ShieldAlert className="w-6 h-6 text-purple-500/80" />
        </div>

        {/* Evidence Strength */}
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs flex items-center justify-between">
          <div>
            <div className="text-2xs font-semibold uppercase tracking-wider text-slate-500">Evidence Strength</div>
            <div className="text-xs font-medium text-slate-800 mt-1">
              <span className="font-semibold text-emerald-700">{stats.evidence_strength_distribution?.COURT_RECORDED || 0}</span> Court Recorded <br />
              <span className="font-semibold text-indigo-700">{stats.evidence_strength_distribution?.PARTY_SUBMISSION || 0}</span> Party Submission
            </div>
          </div>
          <Scale className="w-6 h-6 text-slate-400" />
        </div>

        {/* Case Level Coverage */}
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs flex items-center justify-between">
          <div>
            <div className="text-2xs font-semibold uppercase tracking-wider text-slate-500">Evidence Scope</div>
            <div className="text-xl font-bold text-slate-800 font-mono mt-0.5">{stats.case_level_directions_count}</div>
            <div className="text-3xs text-slate-400">Directions covered at case level</div>
          </div>
          <Layers className="w-6 h-6 text-slate-400" />
        </div>
      </div>

      {/* Autonomous Follow-Up Activity Feed */}
      <AgentActivityFeed />

      {/* Department Compliance Breakdown */}
      <div className="rounded-xl border border-slate-200/80 bg-white shadow-xs overflow-hidden">
        <div className="p-4 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-900">Per-Department Compliance Ledger</h3>
            <p className="text-2xs text-slate-500">Compliance distribution by responsible authority/department</p>
          </div>
          <button onClick={fetchStats} className="text-slate-400 hover:text-slate-600 p-1">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/75 text-2xs font-semibold uppercase tracking-wider text-slate-500">
                <th className="py-3 px-4">Department / Responsible Party</th>
                <th className="py-3 px-4 text-center">Total</th>
                <th className="py-3 px-4 text-center text-emerald-700">Complied</th>
                <th className="py-3 px-4 text-center text-amber-700">Pending</th>
                <th className="py-3 px-4 text-center text-slate-600">Unverified</th>
                <th className="py-3 px-4 text-center text-rose-700">Overdue</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {stats.top_departments?.map((d, idx) => (
                <tr key={idx} className="hover:bg-slate-50/75 transition-colors">
                  <td className="py-3 px-4 font-medium text-slate-800 line-clamp-1">
                    {d.department}
                  </td>
                  <td className="py-3 px-4 text-center font-mono font-semibold text-slate-900">{d.total}</td>
                  <td className="py-3 px-4 text-center font-mono text-emerald-700 font-semibold">{d.complied}</td>
                  <td className="py-3 px-4 text-center font-mono text-amber-700 font-semibold">{d.pending}</td>
                  <td className="py-3 px-4 text-center font-mono text-slate-600">{d.unverified}</td>
                  <td className="py-3 px-4 text-center font-mono text-rose-700 font-semibold">{d.overdue}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
