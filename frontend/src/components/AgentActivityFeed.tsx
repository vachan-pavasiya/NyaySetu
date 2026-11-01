import React, { useState, useEffect } from 'react';
import type { AgentRunItem } from '../types';
import { getApiUrl } from '../config';
import { IconRefresh, IconChevronRight } from './primitives/Icon';

export const AgentActivityFeed: React.FC = () => {
  const [runs, setRuns] = useState<AgentRunItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [rescanning, setRescanning] = useState<boolean>(false);
  const [expandedRunId, setExpandedRunId] = useState<number | null>(null);
  const [rescanMessage, setRescanMessage] = useState<string | null>(null);

  const fetchRuns = async () => {
    try {
      const res = await fetch(getApiUrl('/agent/runs?limit=20'));
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
    const interval = setInterval(fetchRuns, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleRescan = async () => {
    setRescanning(true);
    setRescanMessage(null);
    try {
      const res = await fetch(getApiUrl('/agent/rescan'), { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setRescanMessage(data.message || 'Database rescan complete.');
        await fetchRuns();
      } else {
        setRescanMessage('Rescan failed. Check server log.');
      }
    } catch (err) {
      setRescanMessage(`Rescan failed: ${String(err)}`);
    } finally {
      setRescanning(false);
    }
  };

  const renderOutcomeStamp = (outcome: string) => {
    if (outcome === 'SUCCESS') {
      return (
        <span className="font-mono text-[9px] uppercase tracking-wider border border-[var(--status-complied)] text-[var(--status-complied)] bg-[var(--status-complied-bg)] rounded-[2px] px-1 py-0.5 leading-tight font-semibold">
          SUCCESS
        </span>
      );
    }
    if (outcome === 'NO_CANDIDATES') {
      return (
        <span className="font-mono text-[9px] uppercase tracking-wider border border-[var(--border-rule-strong)] text-[var(--ink-secondary)] bg-[var(--bg-surface-muted)] rounded-[2px] px-1 py-0.5 leading-tight">
          NO CANDIDATES
        </span>
      );
    }
    if (outcome === 'PARTIAL_SUCCESS') {
      return (
        <span className="font-mono text-[9px] uppercase tracking-wider border border-[var(--status-pending)] text-[var(--status-pending)] bg-[var(--status-pending-bg)] rounded-[2px] px-1 py-0.5 leading-tight font-semibold">
          PARTIAL
        </span>
      );
    }
    return (
      <span className="font-mono text-[9px] uppercase tracking-wider border border-[var(--status-overdue)] text-[var(--status-overdue)] bg-[var(--status-overdue-bg)] rounded-[2px] px-1 py-0.5 leading-tight font-semibold">
        FAILED
      </span>
    );
  };

  return (
    <section className="border border-[var(--border-rule)] bg-[var(--bg-surface)]">
      {/* Header bar */}
      <div className="p-3 border-b border-[var(--border-rule)] flex flex-wrap items-center justify-between gap-3 bg-[var(--bg-surface-muted)]">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-serif font-bold text-sm text-[var(--ink-primary)]">
              Follow-Up Activity Record
            </h3>
            <span className="font-mono text-[9px] uppercase tracking-wider text-[var(--accent-oxblood)] border border-[var(--accent-oxblood)] rounded-[2px] px-1 py-0.2">
              Automated Audit
            </span>
          </div>
          <p className="font-sans text-[11px] text-[var(--ink-secondary)] mt-0.5">
            Log of automated cross-order linking, verbatim extraction, and compliance status updates.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={fetchRuns}
            disabled={loading}
            className="p-1 text-[var(--ink-secondary)] hover:text-[var(--ink-primary)] border border-[var(--border-rule)] rounded-[2px] bg-[var(--bg-surface)]"
            title="Refresh activity feed"
          >
            <IconRefresh size={12} className={loading ? 'animate-spin' : ''} />
          </button>

          <button
            onClick={handleRescan}
            disabled={rescanning}
            className="font-mono text-[10px] uppercase tracking-wider font-semibold px-2.5 py-1 border border-[var(--accent-oxblood)] bg-[var(--accent-oxblood)] text-white hover:opacity-90 disabled:opacity-50 rounded-[2px]"
          >
            {rescanning ? 'Scanning Database...' : 'Rescan Database'}
          </button>
        </div>
      </div>

      {rescanMessage && (
        <div className="px-3 py-1.5 border-b border-[var(--border-rule)] bg-[var(--bg-surface-muted)] font-mono text-xs text-[var(--ink-primary)] flex items-center justify-between">
          <span>{rescanMessage}</span>
          <button
            onClick={() => setRescanMessage(null)}
            className="font-mono text-[10px] text-[var(--accent-oxblood)] hover:underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Feed list */}
      <div className="divide-y divide-[var(--border-rule)] max-h-80 overflow-y-auto font-sans text-xs">
        {runs.length === 0 ? (
          <div className="py-8 text-center text-xs text-[var(--ink-secondary)] italic">
            No pipeline runs recorded in this session. Ingest judgments or click &ldquo;Rescan Database&rdquo; to trigger linking.
          </div>
        ) : (
          runs.map((r) => {
            const isExpanded = expandedRunId === r.id;
            return (
              <div key={r.id} className="p-2.5 hover:bg-[var(--bg-surface-muted)] transition-colors">
                <div
                  className="flex items-start justify-between gap-3 cursor-pointer select-none"
                  onClick={() => setExpandedRunId(isExpanded ? null : r.id)}
                >
                  <div className="flex items-start gap-2">
                    <span className="mt-0.5 text-[var(--ink-secondary)]">
                      <IconChevronRight
                        size={12}
                        className={`transform transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                      />
                    </span>
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-[13px] text-[var(--ink-primary)]">
                          {r.message}
                        </span>
                        {renderOutcomeStamp(r.outcome)}
                      </div>
                      <div className="flex items-center gap-2 mt-1 font-mono text-[10px] text-[var(--ink-secondary)]">
                        <span className="uppercase">{r.trigger}</span>
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
                    <span className="font-mono text-xs font-semibold tabular-nums text-[var(--ink-primary)]">
                      {r.directions_updated_count > 0 ? (
                        <span className="text-[var(--status-complied)]">
                          +{r.directions_updated_count} updated
                        </span>
                      ) : (
                        <span className="text-[var(--ink-secondary)]">0 updated</span>
                      )}
                    </span>
                  </div>
                </div>

                {isExpanded && (
                  <div className="mt-2 ml-5 p-2 border border-[var(--border-rule)] bg-[var(--bg-paper)] space-y-1.5 font-mono text-[11px]">
                    <div className="text-[9px] uppercase tracking-wider text-[var(--ink-muted)] font-semibold border-b border-[var(--border-rule)] pb-1">
                      Execution Steps ({r.steps.length})
                    </div>
                    {r.steps.map((st, sIdx) => (
                      <div
                        key={sIdx}
                        className="flex items-center justify-between py-1 px-1.5 border-b border-[var(--border-rule)] last:border-b-0"
                      >
                        <div className="flex items-center gap-1.5">
                          <span className="font-semibold text-[var(--ink-primary)]">{st.step}</span>
                          <span className="text-[var(--ink-muted)]">({st.status})</span>
                        </div>
                        <div className="flex items-center gap-2 text-[var(--ink-secondary)]">
                          {st.details?.candidates_count !== undefined && (
                            <span>candidates: {st.details.candidates_count}</span>
                          )}
                          {st.details?.verdict && (
                            <span className="text-[var(--accent-oxblood)] font-semibold">{st.details.verdict}</span>
                          )}
                          {st.details?.direction_id && <span>dir #{st.details.direction_id}</span>}
                          <span>{st.duration_seconds}s</span>
                        </div>
                      </div>
                    ))}

                    {r.errors && (
                      <div className="mt-1 p-1.5 border border-[var(--status-overdue)] bg-[var(--status-overdue-bg)] text-[var(--status-overdue)]">
                        <strong>Error: </strong>
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
    </section>
  );
};
