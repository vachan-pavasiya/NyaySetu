import React, { useState, useEffect, useRef } from 'react';
import type { IngestJobResponse, BatchAnalyzeResponse, JudgmentSummary } from '../types';
import { getApiUrl } from '../config';
import { PageHeader } from './primitives/PageHeader';
import { DataTable, TableHead, TableRow, TableHeaderCell, TableCell } from './primitives/DataTable';
import { IconRefresh } from './primitives/Icon';

export const IngestView: React.FC = () => {
  // Ingest form state
  const [court, setCourt] = useState<string>('calcutta_appellate_side');
  const [year, setYear] = useState<number>(2023);
  const [limit, setLimit] = useState<number>(10);
  const [isIngesting, setIsIngesting] = useState<boolean>(false);
  const [activeJob, setActiveJob] = useState<IngestJobResponse | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);

  // Analysis state
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false);
  const [analyzeLimit, setAnalyzeLimit] = useState<number>(10);
  const [analyzeResult, setAnalyzeResult] = useState<BatchAnalyzeResponse | null>(null);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);

  // Recent Ingested / Failed judgments list
  const [recentDocs, setRecentDocs] = useState<JudgmentSummary[]>([]);
  const [loadingDocs, setLoadingDocs] = useState<boolean>(false);

  const pollIntervalRef = useRef<any>(null);

  const courtsList = [
    { value: 'calcutta_appellate_side', label: 'Calcutta High Court (Appellate Side)' },
    { value: 'calcutta_original_side', label: 'Calcutta High Court (Original Side)' },
    { value: 'madras', label: 'Madras High Court' },
    { value: 'delhi', label: 'Delhi High Court' },
    { value: 'bombay', label: 'Bombay High Court' },
  ];

  const fetchRecentDocs = async () => {
    setLoadingDocs(true);
    try {
      const res = await fetch(getApiUrl('/judgments?limit=20&offset=0'));
      if (res.ok) {
        const data = await res.json();
        setRecentDocs(data.items || []);
      }
    } catch (err) {
      console.error('Failed to load recent judgments:', err);
    } finally {
      setLoadingDocs(false);
    }
  };

  useEffect(() => {
    fetchRecentDocs();
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, []);

  const startPolling = (jobId: string) => {
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);

    pollIntervalRef.current = setInterval(async () => {
      try {
        const res = await fetch(getApiUrl(`/ingest/jobs/${jobId}`));
        if (res.ok) {
          const job: IngestJobResponse = await res.json();
          setActiveJob(job);

          if (job.status === 'COMPLETED' || job.status === 'FAILED') {
            if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
            setIsIngesting(false);
            fetchRecentDocs();
          }
        }
      } catch (err) {
        console.error('Error polling job status:', err);
      }
    }, 1500);
  };

  const handleStartIngest = async (e: React.FormEvent) => {
    e.preventDefault();
    setJobError(null);
    setIsIngesting(true);
    setActiveJob(null);

    try {
      const res = await fetch(getApiUrl('/ingest'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ court, year: Number(year), limit: Number(limit) }),
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || `Server returned ${res.status}`);
      }

      const job: IngestJobResponse = await res.json();
      setActiveJob(job);
      startPolling(job.job_id);
    } catch (err: any) {
      setJobError(err.message || 'Ingestion request failed');
      setIsIngesting(false);
    }
  };

  const handleStartAnalysis = async () => {
    setAnalyzeError(null);
    setIsAnalyzing(true);
    setAnalyzeResult(null);

    try {
      const res = await fetch(getApiUrl('/analyze/batch'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ limit: Number(analyzeLimit) }),
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || `Server returned ${res.status}`);
      }

      const result: BatchAnalyzeResponse = await res.json();
      setAnalyzeResult(result);
      fetchRecentDocs();
    } catch (err: any) {
      setAnalyzeError(err.message || 'Batch analysis failed');
    } finally {
      setIsAnalyzing(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        volumeOrMeta="AWS Open Data Registry Pipeline · S3 indian-high-court-judgments"
        title="Judgment Ingestion &amp; Operative Direction Extraction"
        deck="Pulls real High Court judgments from AWS Open Data (CC-BY-4.0). Digital vector text is extracted via PyMuPDF with per-document quality checks."
      />

      {/* Two-Column Control Panel */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Stage 1: Ingestion Form */}
        <div className="border border-[var(--border-rule)] bg-[var(--bg-surface)] p-4 space-y-4">
          <div className="border-b border-[var(--border-rule)] pb-2">
            <h2 className="font-serif font-bold text-base text-[var(--ink-primary)]">
              1. Ingest Judgments from AWS Open Data
            </h2>
            <p className="font-sans text-xs text-[var(--ink-secondary)] mt-0.5">
              Connects directly to the public unsigned S3 bucket without credentials.
            </p>
          </div>

          <form onSubmit={handleStartIngest} className="space-y-3 font-sans text-xs">
            <div>
              <label className="font-mono text-[10px] uppercase tracking-wider text-[var(--ink-muted)] block mb-1 font-semibold">
                High Court Jurisdiction
              </label>
              <select
                value={court}
                onChange={(e) => setCourt(e.target.value)}
                disabled={isIngesting}
                className="w-full px-2.5 py-1.5 font-mono text-xs border border-[var(--border-rule-strong)] bg-[var(--bg-paper)] text-[var(--ink-primary)] rounded-[2px]"
              >
                {courtsList.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="font-mono text-[10px] uppercase tracking-wider text-[var(--ink-muted)] block mb-1 font-semibold">
                  Judicial Year
                </label>
                <input
                  type="number"
                  min={2000}
                  max={2026}
                  value={year}
                  onChange={(e) => setYear(Number(e.target.value))}
                  disabled={isIngesting}
                  className="w-full px-2.5 py-1.5 font-mono text-xs border border-[var(--border-rule-strong)] bg-[var(--bg-paper)] text-[var(--ink-primary)] rounded-[2px]"
                />
              </div>

              <div>
                <label className="font-mono text-[10px] uppercase tracking-wider text-[var(--ink-muted)] block mb-1 font-semibold">
                  Batch Size (Max 20)
                </label>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={limit}
                  onChange={(e) => setLimit(Number(e.target.value))}
                  disabled={isIngesting}
                  className="w-full px-2.5 py-1.5 font-mono text-xs border border-[var(--border-rule-strong)] bg-[var(--bg-paper)] text-[var(--ink-primary)] rounded-[2px]"
                />
              </div>
            </div>

            {/* Thin progress rule during ingestion */}
            {isIngesting && (
              <div className="space-y-1 pt-1">
                <div className="h-[2px] w-full bg-[var(--bg-surface-muted)] overflow-hidden">
                  <div className="h-full bg-[var(--accent-oxblood)] animate-pulse w-2/3" />
                </div>
                <div className="font-mono text-[10px] text-[var(--ink-secondary)]">
                  Retrieving orders from S3 bucket...
                </div>
              </div>
            )}

            {jobError && (
              <div className="p-2 border border-[var(--status-overdue)] bg-[var(--status-overdue-bg)] text-[var(--status-overdue)] text-xs">
                <strong>Ingestion Error:</strong> {jobError}
              </div>
            )}

            <button
              type="submit"
              disabled={isIngesting}
              className="w-full font-mono text-xs uppercase tracking-wider font-semibold py-2 border border-[var(--accent-oxblood)] bg-[var(--accent-oxblood)] text-white hover:opacity-90 disabled:opacity-50 rounded-[2px]"
            >
              {isIngesting ? 'Ingesting from S3...' : 'Start S3 Ingestion Job'}
            </button>
          </form>

          {/* Active Job Status */}
          {activeJob && (
            <div className="border border-[var(--border-rule)] bg-[var(--bg-paper)] p-3 space-y-1.5 font-mono text-xs">
              <div className="flex items-center justify-between">
                <span className="font-bold text-[var(--ink-primary)]">Job #{activeJob.job_id.slice(0, 8)}</span>
                <span className="uppercase text-[10px] text-[var(--accent-oxblood)] font-semibold">
                  {activeJob.status}
                </span>
              </div>
              <div className="text-[11px] text-[var(--ink-secondary)]">
                Orders: {activeJob.succeeded || 0} succeeded · {activeJob.failed || 0} unreadable / failed
              </div>
            </div>
          )}
        </div>

        {/* Stage 2: Batch Analysis Control */}
        <div className="border border-[var(--border-rule)] bg-[var(--bg-surface)] p-4 space-y-4">
          <div className="border-b border-[var(--border-rule)] pb-2">
            <h2 className="font-serif font-bold text-base text-[var(--ink-primary)]">
              2. Extract Operative Directions &amp; Deadlines
            </h2>
            <p className="font-sans text-xs text-[var(--ink-secondary)] mt-0.5">
              Segments operative text, extracts responsible parties, and verifies verbatim source quotes.
            </p>
          </div>

          <div className="space-y-3 font-sans text-xs">
            <div>
              <label className="font-mono text-[10px] uppercase tracking-wider text-[var(--ink-muted)] block mb-1 font-semibold">
                Orders to Analyze in Batch
              </label>
              <input
                type="number"
                min={1}
                max={20}
                value={analyzeLimit}
                onChange={(e) => setAnalyzeLimit(Number(e.target.value))}
                disabled={isAnalyzing}
                className="w-full px-2.5 py-1.5 font-mono text-xs border border-[var(--border-rule-strong)] bg-[var(--bg-paper)] text-[var(--ink-primary)] rounded-[2px]"
              />
            </div>

            <div className="border border-[var(--border-rule)] bg-[var(--bg-paper)] p-3 space-y-1 font-sans text-xs text-[var(--ink-secondary)]">
              <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--ink-muted)] font-semibold">
                Autonomous Verification Loop
              </div>
              <p className="leading-normal">
                Directions are checked by a deterministic verifier. Source quotes must be verbatim substrings of the judgment text. Deadline windows are calculated via deterministic Python arithmetic.
              </p>
            </div>

            {/* Thin progress rule during analysis */}
            {isAnalyzing && (
              <div className="space-y-1 pt-1">
                <div className="h-[2px] w-full bg-[var(--bg-surface-muted)] overflow-hidden">
                  <div className="h-full bg-[var(--ink-primary)] animate-pulse w-3/4" />
                </div>
                <div className="font-mono text-[10px] text-[var(--ink-secondary)]">
                  Segmenting orders, extracting directions, verifying quotes...
                </div>
              </div>
            )}

            {analyzeError && (
              <div className="p-2 border border-[var(--status-overdue)] bg-[var(--status-overdue-bg)] text-[var(--status-overdue)] text-xs">
                <strong>Analysis Error:</strong> {analyzeError}
              </div>
            )}

            <button
              onClick={handleStartAnalysis}
              disabled={isAnalyzing}
              className="w-full font-mono text-xs uppercase tracking-wider font-semibold py-2 border border-[var(--ink-primary)] bg-[var(--ink-primary)] text-[var(--bg-paper)] hover:bg-[var(--accent-oxblood)] hover:border-[var(--accent-oxblood)] transition-colors disabled:opacity-50 rounded-[2px]"
            >
              {isAnalyzing ? 'Analyzing Judgments...' : 'Run Operative Extraction Batch'}
            </button>

            {/* Batch Analysis Result Summary */}
            {analyzeResult && (
              <div className="border border-[var(--border-rule)] bg-[var(--bg-paper)] p-3 space-y-1 font-mono text-xs">
                <div className="font-bold text-[var(--ink-primary)]">
                  Batch Complete: {analyzeResult.total_judgments} orders analyzed
                </div>
                <div className="text-[11px] text-[var(--status-complied)] font-semibold">
                  +{analyzeResult.total_directions} operative directions extracted
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Recent Ingested Documents & Document Quality Table */}
      <div className="space-y-2">
        <div className="flex items-baseline justify-between">
          <h2 className="font-serif font-bold text-base text-[var(--ink-primary)]">
            Recent Judgment Ingestions &amp; Document Quality
          </h2>
          <button
            onClick={fetchRecentDocs}
            disabled={loadingDocs}
            className="font-mono text-xs text-[var(--accent-oxblood)] hover:underline inline-flex items-center gap-1"
          >
            <IconRefresh size={11} className={loadingDocs ? 'animate-spin' : ''} />
            <span>Refresh Table</span>
          </button>
        </div>

        <DataTable>
          <TableHead>
            <tr>
              <TableHeaderCell>Case Reference</TableHeaderCell>
              <TableHeaderCell>Judicial Year</TableHeaderCell>
              <TableHeaderCell>Parties (Title)</TableHeaderCell>
              <TableHeaderCell align="center">Vector Text Quality</TableHeaderCell>
              <TableHeaderCell align="right">Pipeline Status &amp; Failure Reason</TableHeaderCell>
            </tr>
          </TableHead>
          <tbody>
            {recentDocs.length === 0 ? (
              <TableRow>
                <TableCell className="text-center italic" align="center">
                  No judgments ingested yet.
                </TableCell>
              </TableRow>
            ) : (
              recentDocs.map((doc) => {
                const isFailed = doc.status.includes('FAIL');
                const isAnalyzed = doc.status === 'ANALYZED';

                return (
                  <TableRow key={doc.id}>
                    <TableCell>
                      <span className="font-mono font-bold text-xs text-[var(--ink-primary)]">
                        {doc.case_number}
                      </span>
                    </TableCell>
                    <TableCell className="font-mono text-xs tabular-nums">
                      {doc.year}
                    </TableCell>
                    <TableCell>
                      <div className="font-serif text-xs text-[var(--ink-secondary)] truncate max-w-sm">
                        {doc.petitioner || 'Petitioner'} v. {doc.respondent || 'State of West Bengal'}
                      </div>
                    </TableCell>
                    <TableCell align="center">
                      <span className="font-mono text-xs tabular-nums">
                        {doc.text_quality !== undefined ? `${(doc.text_quality * 100).toFixed(0)}%` : '—'}
                      </span>
                    </TableCell>
                    <TableCell align="right">
                      <div className="flex flex-col items-end gap-0.5">
                        <span
                          className={`font-mono text-[9px] uppercase tracking-wider border rounded-[2px] px-1 py-0.5 font-semibold ${
                            isAnalyzed
                              ? 'border-[var(--status-complied)] text-[var(--status-complied)] bg-[var(--status-complied-bg)]'
                              : isFailed
                              ? 'border-[var(--status-overdue)] text-[var(--status-overdue)] bg-[var(--status-overdue-bg)]'
                              : 'border-[var(--border-rule-strong)] text-[var(--ink-secondary)] bg-[var(--bg-surface-muted)]'
                          }`}
                        >
                          {doc.status}
                        </span>
                        {isFailed && (
                          <span className="font-sans text-[10px] text-[var(--status-overdue)]">
                            Scanned or unreadable vector text
                          </span>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </tbody>
        </DataTable>
      </div>
    </div>
  );
};
