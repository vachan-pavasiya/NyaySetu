import React, { useState, useEffect } from 'react';
import { Activity, RefreshCw, CheckCircle2, AlertCircle, Clock, ChevronDown, ChevronRight, Play } from 'lucide-react';
import type { AgentRunItem } from '../types';

export const AgentActivityFeed: React.FC = () => {
  const [runs, setRuns] = useState<AgentRunItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [rescanning, setRescanning] = useState<boolean>(false);
  const [expandedRunId, setExpandedRunId] = useState<number | null>(null);
  const [rescanMessage, setRescanMessage] = useState<string | null>(null);

  const fetchRuns = async () => {
    try {
      let res = await fetch('/api/agent/runs?limit=20');
      if (!res.ok) {
        res = await fetch('http://127.0.0.1:8000/agent/runs?limit=20');
      }
      if (res.ok) {
        const data = await res.json();
        setRuns(data.runs || []);
      }
    } catch (err) {
      console.error('Failed to fetch agent runs:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRuns();
    const interval = setInterval(fetchRuns, 10000); // Poll every 10s for new runs
    return () => clearInterval(interval);
  }, []);

  const handleRescan = async () => {
    setRescanning(true);
    setRescanMessage(null);
    try {
      let res = await fetch('/api/agent/rescan', { method: 'POST' });
      if (!res.ok) {
        res = await fetch('http://127.0.0.1:8000/agent/rescan', { method: 'POST' });
      }
      if (res.ok) {
        const data = await res.json();
        setRescanMessage(data.message || 'Rescan completed successfully');
        await fetchRuns();
      } else {
        setRescanMessage('Rescan failed. Check server logs.');
      }
    } catch (err) {
      setRescanMessage(`Rescan failed: ${String(err)}`);
    } finally {
      setRescanning(false);
    }
  };

  const getOutcomeBadge = (outcome: string) => {
    switch (outcome) {
      case 'SUCCESS':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-3xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
            <CheckCircle2 className="w-2.5 h-2.5" /> SUCCESS
          </span>
        );
      case 'NO_CANDIDATES':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-3xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
            NO CANDIDATES
          </span>
        );
      case 'PARTIAL_SUCCESS':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-3xs font-semibold bg-amber-100 text-amber-800 border border-amber-200">
            <AlertCircle className="w-2.5 h-2.5" /> PARTIAL
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-3xs font-semibold bg-rose-100 text-rose-800 border border-rose-200">
            <AlertCircle className="w-2.5 h-2.5" /> FAILED
          </span>
        );
    }
  };

  return (
    <div className="rounded-xl border border-slate-200/80 bg-white shadow-xs overflow-hidden">
      {/* Activity Header */}
      <div className="p-4 border-b border-slate-100 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 border border-indigo-100">
            <Activity className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-slate-900">Autonomous Follow-Up Activity Feed</h3>
              <span className="text-3xs font-semibold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
                Agent Loop Active
              </span>
            </div>
            <p className="text-2xs text-slate-500">
              Live background monitoring of newly ingested orders, follow-up linking, and status changes
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={fetchRuns}
            disabled={loading}
            className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
            title="Refresh feed"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>

          <button
            onClick={handleRescan}
            disabled={rescanning}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white shadow-xs transition-all disabled:opacity-50"
          >
            {rescanning ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>Scanning DB...</span>
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5" />
                <span>Rescan Database</span>
              </>
            )}
          </button>
        </div>
      </div>

      {rescanMessage && (
        <div className="px-4 py-2 bg-indigo-50/70 border-b border-indigo-100 text-xs text-indigo-900 flex items-center justify-between">
          <span>{rescanMessage}</span>
          <button onClick={() => setRescanMessage(null)} className="text-xs text-indigo-500 hover:text-indigo-800">
            Dismiss
          </button>
        </div>
      )}

      {/* Feed List */}
      <div className="divide-y divide-slate-100 max-h-96 overflow-y-auto">
        {runs.length === 0 ? (
          <div className="py-12 text-center text-xs text-slate-400">
            <Clock className="w-5 h-5 mx-auto mb-1.5 text-slate-300" />
            No agent activity runs recorded yet. Click &quot;Rescan Database&quot; or ingest judgments.
          </div>
        ) : (
          runs.map((r) => {
            const isExpanded = expandedRunId === r.id;
            return (
              <div key={r.id} className="p-4 hover:bg-slate-50/60 transition-colors">
                <div
                  className="flex items-start justify-between gap-3 cursor-pointer"
                  onClick={() => setExpandedRunId(isExpanded ? null : r.id)}
                >
                  <div className="flex items-start gap-2.5">
                    <button className="mt-0.5 text-slate-400 hover:text-slate-600">
                      {isExpanded ? (
                        <ChevronDown className="w-3.5 h-3.5" />
                      ) : (
                        <ChevronRight className="w-3.5 h-3.5" />
                      )}
                    </button>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-slate-900">{r.message}</span>
                        {getOutcomeBadge(r.outcome)}
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-2xs text-slate-400">
                        <span className="font-mono uppercase">{r.trigger}</span>
                        <span>•</span>
                        <span>{r.duration_seconds.toFixed(2)}s runtime</span>
                        <span>•</span>
                        <span>{r.steps.length} state steps</span>
                        <span>•</span>
                        <span>{new Date(r.created_at).toLocaleTimeString()}</span>
                      </div>
                    </div>
                  </div>

                  <div className="text-right shrink-0">
                    <div className="text-2xs font-mono font-medium text-slate-600">
                      {r.directions_updated_count > 0 ? (
                        <span className="text-emerald-700 font-semibold font-mono">
                          +{r.directions_updated_count} updated
                        </span>
                      ) : (
                        <span>0 updated</span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Expanded State Graph & Step Telemetry */}
                {isExpanded && (
                  <div className="mt-3 ml-6 p-3 rounded-lg bg-slate-50 border border-slate-200/80 space-y-2">
                    <div className="text-3xs font-bold uppercase tracking-wider text-slate-400">
                      Pipeline Execution Steps
                    </div>
                    <div className="space-y-1.5 font-mono text-2xs">
                      {r.steps.map((st, sIdx) => (
                        <div
                          key={sIdx}
                          className="flex items-center justify-between py-1 px-2 rounded bg-white border border-slate-100"
                        >
                          <div className="flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-indigo-500" />
                            <span className="font-semibold text-slate-800">{st.step}</span>
                            <span className="text-3xs text-slate-400">({st.status})</span>
                          </div>
                          <div className="flex items-center gap-3 text-slate-500">
                            {st.details?.candidates_count !== undefined && (
                              <span>candidates: {st.details.candidates_count}</span>
                            )}
                            {st.details?.verdict && (
                              <span className="text-indigo-600 font-semibold">{st.details.verdict}</span>
                            )}
                            {st.details?.direction_id && <span>dir #{st.details.direction_id}</span>}
                            <span>{st.duration_seconds}s</span>
                          </div>
                        </div>
                      ))}
                    </div>

                    {r.errors && (
                      <div className="mt-2 p-2 rounded bg-rose-50 border border-rose-200 text-2xs text-rose-800">
                        <span className="font-bold">Errors: </span>
                        {r.errors}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

