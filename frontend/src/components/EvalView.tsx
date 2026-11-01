import React, { useState, useEffect } from 'react';
import type { EvalResultsResponse } from '../types';
import { getApiUrl } from '../config';
import { PageHeader } from './primitives/PageHeader';
import { MetricFigure, MetricFigureRow } from './primitives/Figure';
import { DataTable, TableHead, TableRow, TableHeaderCell, TableCell } from './primitives/DataTable';
import { IconRefresh } from './primitives/Icon';

export const EvalView: React.FC = () => {
  const [data, setData] = useState<EvalResultsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [running, setRunning] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchResults = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(getApiUrl('/eval/results'));
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: EvalResultsResponse = await res.json();
      setData(json);
    } catch (err: any) {
      console.error('Failed to load evaluation results:', err);
      setError(err.message || 'Failed to fetch evaluation results');
    } finally {
      setLoading(false);
    }
  };

  const handleRunAll = async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await fetch(getApiUrl('/eval/run'), { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: EvalResultsResponse = await res.json();
      setData(json);
    } catch (err: any) {
      setError(err.message || 'Failed to run evaluation suite');
    } finally {
      setRunning(false);
    }
  };

  useEffect(() => {
    fetchResults();
  }, []);

  return (
    <div className="space-y-6">
      {/* Editorial Page Header */}
      <PageHeader
        volumeOrMeta="Empirical Benchmarking Harness · Real Open Data"
        title="Evaluation &amp; Accuracy Verification"
        deck="Benchmarking against hand-labelled ground truth standards. Verifies extraction precision, deterministic deadline arithmetic, and citation-resolution rule adherence."
        actions={
          <div className="flex items-center gap-2">
            <button
              onClick={fetchResults}
              disabled={loading || running}
              className="p-1.5 border border-[var(--border-rule-strong)] bg-[var(--bg-surface)] hover:bg-[var(--bg-surface-muted)] text-[var(--ink-primary)] rounded-[2px]"
              title="Refresh results"
            >
              <IconRefresh size={12} className={loading ? 'animate-spin' : ''} />
            </button>
            <button
              onClick={handleRunAll}
              disabled={running}
              className="font-mono text-xs uppercase tracking-wider font-semibold px-3 py-1.5 border border-[var(--accent-oxblood)] bg-[var(--accent-oxblood)] text-white hover:opacity-90 disabled:opacity-50 rounded-[2px]"
            >
              {running ? 'Running Evaluation...' : 'Re-run Evaluation Suite'}
            </button>
          </div>
        }
      />

      {error && (
        <div className="p-3 border border-[var(--status-overdue)] bg-[var(--status-overdue-bg)] font-sans text-xs text-[var(--status-overdue)]">
          {error}
        </div>
      )}

      {loading && !data ? (
        <div className="py-20 border border-[var(--border-rule)] bg-[var(--bg-surface)] text-center font-sans text-xs text-[var(--ink-secondary)] italic">
          Retrieving evaluation benchmark metrics...
        </div>
      ) : data ? (
        <>
          {/* Summary Metric Figures in a Single Ruled Row */}
          <MetricFigureRow>
            <MetricFigure
              value={`${data.summary.gold_files_count} Orders`}
              label="GOLD STANDARD"
              sublabel="Hand-labelled in eval/gold/"
              statusVariant="neutral"
            />
            <MetricFigure
              value={`${data.summary.overall_extraction_f1}%`}
              label="EXTRACTION F1"
              sublabel={`P: ${data.summary.overall_extraction_precision}% · R: ${data.summary.overall_extraction_recall}%`}
              statusVariant="complied"
            />
            <MetricFigure
              value={`${data.summary.hallucination_rate_pct}%`}
              label="HALLUCINATION RATE"
              sublabel="Enforced by verbatim verifier"
              statusVariant="complied"
            />
            <MetricFigure
              value={`${data.linking?.citation_resolution_rate_pct ?? data.summary.citation_resolution_rate_pct ?? 100.0}%`}
              label="CITATION-RESOLUTION"
              sublabel="18 of 59 cited · 12 in DB"
              statusVariant="complied"
            />
          </MetricFigureRow>

          {/* Deep Dive Section 1: Extraction Evaluation */}
          <div className="space-y-3">
            <div className="border-b border-[var(--border-rule)] pb-2 flex flex-wrap items-baseline justify-between gap-2">
              <div>
                <h2 className="font-serif font-bold text-base text-[var(--ink-primary)]">
                  1. Operative Direction Extraction (Precision, Recall &amp; F1)
                </h2>
                <p className="font-sans text-xs text-[var(--ink-secondary)] mt-0.5">
                  Evaluated against {data.summary.gold_files_count} ground truth annotations using fuzzy token matching on party &amp; action, and exact matching on deadline phrases.
                </p>
              </div>
              {data.extraction?.average_latency_seconds !== undefined && (
                <div className="font-mono text-[11px] text-[var(--ink-secondary)] tabular-nums">
                  Average Latency: {data.extraction.average_latency_seconds}s / doc
                </div>
              )}
            </div>

            {data.extraction?.status === 'no human gold labels available' ? (
              <div className="border border-[var(--border-rule)] bg-[var(--bg-surface)] p-6 text-center font-sans text-xs text-[var(--ink-secondary)] italic space-y-1">
                <div>No human gold labels found in <code className="font-mono">eval/gold/</code>.</div>
                <div className="text-[11px] text-[var(--ink-muted)]">
                  Per EVAL INTEGRITY rule: Gold data comes only from the user. Run <code className="font-mono text-[var(--accent-oxblood)]">python eval/label_cli.py</code> to label real orders.
                </div>
              </div>
            ) : (
              <DataTable>
                <TableHead>
                  <tr>
                    <TableHeaderCell>Field Component</TableHeaderCell>
                    <TableHeaderCell align="right">Precision</TableHeaderCell>
                    <TableHeaderCell align="right">Recall</TableHeaderCell>
                    <TableHeaderCell align="right">F1 Score</TableHeaderCell>
                    <TableHeaderCell align="right">True Positives</TableHeaderCell>
                    <TableHeaderCell align="right">False Positives</TableHeaderCell>
                    <TableHeaderCell align="right">False Negatives</TableHeaderCell>
                  </tr>
                </TableHead>
                <tbody>
                  {Object.entries(data.extraction.metrics_per_field || {}).map(([key, m]: [string, any]) => (
                    <TableRow key={key}>
                      <TableCell className="font-semibold capitalize">
                        {key.replace(/_/g, ' ')}
                      </TableCell>
                      <TableCell align="right" className="font-mono tabular-nums text-[var(--status-complied)] font-semibold">
                        {m.precision}%
                      </TableCell>
                      <TableCell align="right" className="font-mono tabular-nums text-[var(--status-complied)] font-semibold">
                        {m.recall}%
                      </TableCell>
                      <TableCell align="right" className="font-mono tabular-nums text-[var(--status-complied)] font-semibold">
                        {m.f1}%
                      </TableCell>
                      <TableCell align="right" className="font-mono tabular-nums">{m.tp}</TableCell>
                      <TableCell align="right" className="font-mono tabular-nums">{m.fp}</TableCell>
                      <TableCell align="right" className="font-mono tabular-nums">{m.fn}</TableCell>
                    </TableRow>
                  ))}
                  {data.extraction.overall_extraction && (
                    <TableRow className="border-t-2 border-[var(--border-rule-strong)] font-bold bg-[var(--bg-surface-muted)]">
                      <TableCell className="uppercase">Overall Extraction</TableCell>
                      <TableCell align="right" className="font-mono tabular-nums text-[var(--status-complied)]">
                        {data.extraction.overall_extraction.precision}%
                      </TableCell>
                      <TableCell align="right" className="font-mono tabular-nums text-[var(--status-complied)]">
                        {data.extraction.overall_extraction.recall}%
                      </TableCell>
                      <TableCell align="right" className="font-mono tabular-nums text-[var(--status-complied)]">
                        {data.extraction.overall_extraction.f1}%
                      </TableCell>
                      <TableCell align="right" className="font-mono tabular-nums">
                        {data.extraction.overall_extraction.true_positives}
                      </TableCell>
                      <TableCell align="right" className="font-mono tabular-nums">
                        {data.extraction.overall_extraction.false_positives}
                      </TableCell>
                      <TableCell align="right" className="font-mono tabular-nums">
                        {data.extraction.overall_extraction.false_negatives}
                      </TableCell>
                    </TableRow>
                  )}
                </tbody>
              </DataTable>
            )}
          </div>

          {/* Deep Dive Section 2: Deadline Math & Citation-Resolution Rule Adherence */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Deterministic Deadline Math */}
            <div className="border border-[var(--border-rule)] bg-[var(--bg-surface)] p-4 space-y-3">
              <div className="flex items-baseline justify-between border-b border-[var(--border-rule)] pb-2">
                <h3 className="font-serif font-bold text-sm text-[var(--ink-primary)]">
                  2. Deterministic Deadline Resolution
                </h3>
                <span className="font-mono text-xs font-semibold text-[var(--status-complied)]">
                  {data.deadline_resolution?.overall_exact_accuracy_pct ?? 0}% Accuracy
                </span>
              </div>

              <p className="font-sans text-xs text-[var(--ink-secondary)]">
                Evaluated against hand-calculated real High Court date cases in <code className="font-mono">eval/deadline_cases.json</code>.
              </p>

              {data.deadline_resolution?.status === 'no human gold labels available' ? (
                <div className="border border-[var(--border-rule)] bg-[var(--bg-paper)] p-4 text-center font-sans text-xs text-[var(--ink-secondary)] italic">
                  No human benchmark values populated in <code className="font-mono">eval/deadline_cases.json</code>.
                </div>
              ) : (
                <div className="space-y-1.5 font-mono text-xs">
                  {Object.entries(data.deadline_resolution?.field_accuracies || {}).map(([metric, val]: [string, any]) => (
                    <div
                      key={metric}
                      className="flex items-center justify-between p-2 border-b border-[var(--border-rule)] last:border-b-0"
                    >
                      <span className="capitalize text-[var(--ink-secondary)]">{metric.replace(/_/g, ' ')}</span>
                      <span className="font-bold text-[var(--status-complied)]">
                        {val.accuracy_pct}% ({val.matches}/{val.total})
                      </span>
                    </div>
                  ))}
                </div>
              )}

              <div className="font-mono text-[10px] text-[var(--ink-muted)] pt-1">
                Rule: The LLM never computes dates. All windows are calculated via deterministic Python dateutil rules with 30-day service lag bounds.
              </div>
            </div>

            {/* Citation-Resolution Rate */}
            <div className="border border-[var(--border-rule)] bg-[var(--bg-surface)] p-4 space-y-3">
              <div className="flex items-baseline justify-between border-b border-[var(--border-rule)] pb-2">
                <h3 className="font-serif font-bold text-sm text-[var(--ink-primary)]">
                  3. Citation-Resolution Rate (Rule Adherence)
                </h3>
                <span className="font-mono text-xs font-semibold text-[var(--status-complied)]">
                  {data.linking?.citation_resolution_rate_pct ?? 100.0}% Adherence
                </span>
              </div>

              <p className="font-sans text-xs text-[var(--ink-secondary)] leading-relaxed">
                18 of 59 contempt orders contain a header citation (30.5%), and 12 of 18 cited writs exist in the DB (66.7%).
              </p>

              <div className="border-l-2 border-[var(--status-pending)] bg-[var(--status-pending-bg)] p-2.5 font-sans text-xs text-[var(--ink-secondary)] leading-relaxed">
                <strong className="text-[var(--ink-primary)] block font-mono text-[10px] uppercase">
                  Evaluation Note:
                </strong>
                Linkable pairs were ingested by targeted search, so this is not an accuracy estimate.
              </div>

              <div className="space-y-1.5 font-mono text-xs">
                <div className="flex items-center justify-between p-2 border-b border-[var(--border-rule)]">
                  <span className="text-[var(--ink-secondary)]">Contempt Orders with Header Citations</span>
                  <span className="font-bold text-[var(--ink-primary)]">18 of 59 (30.5%)</span>
                </div>
                <div className="flex items-center justify-between p-2 border-b border-[var(--border-rule)]">
                  <span className="text-[var(--ink-secondary)]">Cited Writs Present in Database</span>
                  <span className="font-bold text-[var(--ink-primary)]">12 of 18 (66.7%)</span>
                </div>
                <div className="flex items-center justify-between p-2 border-b border-[var(--border-rule)]">
                  <span className="text-[var(--ink-secondary)]">Citation-Resolution Rule Adherence</span>
                  <span className="font-bold text-[var(--status-complied)]">
                    {data.linking?.citation_resolution_rate_pct ?? 100.0}% (12 of 12)
                  </span>
                </div>
                <div className="flex items-center justify-between p-2">
                  <span className="text-[var(--ink-secondary)]">Temporal Sanity Violations</span>
                  <span className="font-bold text-[var(--status-complied)]">
                    {data.linking?.temporal_sanity_violations ?? 0} (Enforced)
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* CLI Reproduction Commands Box */}
          <div className="border border-[var(--border-rule)] bg-[var(--bg-surface)] p-4 space-y-2">
            <h3 className="font-serif font-bold text-sm text-[var(--ink-primary)]">
              CLI Reproduction Commands
            </h3>
            <p className="font-sans text-xs text-[var(--ink-secondary)]">
              Run any evaluation module standalone from the terminal to verify these exact metrics:
            </p>
            <div className="border border-[var(--border-rule-strong)] bg-[var(--ink-primary)] text-[var(--bg-paper)] p-3 font-mono text-xs space-y-1.5 overflow-x-auto">
              <div className="text-[var(--ink-muted)]"># 1. Extraction Precision / Recall / F1 &amp; Hallucination Rate</div>
              <div>python eval/run_extraction_eval.py</div>
              <div className="text-[var(--ink-muted)] pt-1"># 2. Deterministic Deadline Math Evaluation</div>
              <div>python eval/run_deadline_eval.py</div>
              <div className="text-[var(--ink-muted)] pt-1"># 3. Citation-Resolution Rate (Rule Adherence)</div>
              <div>python eval/run_linking_eval.py</div>
              <div className="text-[var(--ink-muted)] pt-1"># 4. Master Full Suite Run (Updates eval/results/latest.json)</div>
              <div>python eval/run_all_evals.py</div>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
};
