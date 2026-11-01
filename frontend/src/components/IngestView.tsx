import React, { useState, useEffect, useRef } from 'react';
import { DownloadCloud, Play, RefreshCw, CheckCircle2, AlertTriangle, XCircle, Sparkles } from 'lucide-react';
import type { IngestJobResponse, BatchAnalyzeResponse, JudgmentSummary } from '../types';
import { getApiUrl } from '../config';

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

  // Fetch recent judgments to inspect live failures & successes
  const fetchRecentDocs = async () => {
    setLoadingDocs(true);
    try {
      const res = await fetch(getApiUrl('/judgments?limit=15&offset=0'));
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

  // Poll Ingestion Job status
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

  // Trigger Ingestion
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
      setJobError(err.message || 'Failed to trigger ingestion job');
      setIsIngesting(false);
    }
  };

  // Trigger Batch Analysis
  const handleStartAnalysis = async () => {
    setIsAnalyzing(true);
    setAnalyzeError(null);
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
      setAnalyzeError(err.message || 'Failed to run batch analysis');
    } finally {
      setIsAnalyzing(false);
    }
  };

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      {/* Page Header */}
      <div>
        <h2 className="text-xl font-bold text-slate-900 tracking-tight">
          Live Data Ingestion & Agentic Analysis Pipeline
        </h2>
        <p className="text-xs text-slate-500 mt-1">
          Trigger real ingestion directly from the AWS Open Data bucket (CC-BY-4.0, unsigned S3) into SQLite, run text extraction, and analyze directions with Gemini.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Card 1: Ingest Form */}
        <div className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-xs space-y-4">
          <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
            <DownloadCloud className="w-4 h-4 text-blue-600" />
            <h3 className="text-sm font-bold text-slate-900">1. Ingest Real Court Orders</h3>
          </div>

          <form onSubmit={handleStartIngest} className="space-y-4">
            <div className="space-y-1">
              <label className="text-2xs font-bold uppercase tracking-wider text-slate-500">Court</label>
              <select
                value={court}
                onChange={(e) => setCourt(e.target.value)}
                disabled={isIngesting}
                className="w-full text-xs rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 focus:outline-none focus:ring-1 focus:ring-slate-900"
              >
                {courtsList.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="text-2xs font-bold uppercase tracking-wider text-slate-500">Year</label>
                <select
                  value={year}
                  onChange={(e) => setYear(Number(e.target.value))}
                  disabled={isIngesting}
                  className="w-full text-xs rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 focus:outline-none focus:ring-1 focus:ring-slate-900"
                >
                  <option value={2024}>2024</option>
                  <option value={2023}>2023</option>
                  <option value={2022}>2022</option>
                  <option value={2021}>2021</option>
                  <option value={2020}>2020</option>
                </select>
              </div>

              <div className="space-y-1">
                <label className="text-2xs font-bold uppercase tracking-wider text-slate-500">
                  Limit (Docs)
                </label>
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={limit}
                  onChange={(e) => setLimit(Number(e.target.value))}
                  disabled={isIngesting}
                  className="w-full text-xs rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 focus:outline-none focus:ring-1 focus:ring-slate-900"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={isIngesting}
              className={`w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg text-xs font-semibold text-white transition-all shadow-xs ${
                isIngesting
                  ? 'bg-slate-400 cursor-not-allowed'
                  : 'bg-slate-900 hover:bg-slate-800'
              }`}
            >
              {isIngesting ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Ingesting Real Orders from AWS...</span>
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5 fill-current" />
                  <span>Start Live Ingestion</span>
                </>
              )}
            </button>
          </form>

          {jobError && (
            <div className="rounded-lg bg-rose-50 border border-rose-200 p-3 text-2xs text-rose-700">
              {jobError}
            </div>
          )}

          {/* Live Progress Card */}
          {activeJob && (
            <div className="rounded-lg bg-slate-50 border border-slate-200 p-4 space-y-3 mt-4">
              <div className="flex items-center justify-between">
                <span className="font-mono text-2xs font-semibold text-slate-700">
                  Job: {activeJob.job_id.slice(0, 8)}...
                </span>
                <span
                  className={`text-3xs font-bold px-2 py-0.5 rounded font-mono ${
                    activeJob.status === 'COMPLETED'
                      ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
                      : activeJob.status === 'RUNNING'
                      ? 'bg-blue-100 text-blue-800 animate-pulse'
                      : 'bg-amber-100 text-amber-800'
                  }`}
                >
                  {activeJob.status}
                </span>
              </div>

              {/* Progress bar */}
              <div className="space-y-1">
                <div className="flex justify-between text-3xs font-medium text-slate-600">
                  <span>Processed: {activeJob.processed} / {activeJob.total || activeJob.limit}</span>
                  <span>
                    {activeJob.total > 0
                      ? `${Math.round((activeJob.processed / activeJob.total) * 100)}%`
                      : '0%'}
                  </span>
                </div>
                <div className="w-full bg-slate-200 h-2 rounded-full overflow-hidden">
                  <div
                    className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                    style={{
                      width: `${
                        activeJob.total > 0
                          ? Math.min(100, Math.round((activeJob.processed / activeJob.total) * 100))
                          : 0
                      }%`,
                    }}
                  />
                </div>
              </div>

              {/* Counts Breakdown */}
              <div className="grid grid-cols-3 gap-2 text-center text-2xs pt-1">
                <div className="bg-white p-2 rounded border border-slate-200">
                  <span className="text-slate-400 block text-3xs">Succeeded</span>
                  <span className="font-bold text-emerald-700 font-mono">{activeJob.succeeded}</span>
                </div>
                <div className="bg-white p-2 rounded border border-slate-200">
                  <span className="text-slate-400 block text-3xs">Failed / Unreadable</span>
                  <span className="font-bold text-rose-700 font-mono">{activeJob.failed}</span>
                </div>
                <div className="bg-white p-2 rounded border border-slate-200">
                  <span className="text-slate-400 block text-3xs">Avg Sec/Doc</span>
                  <span className="font-bold text-slate-800 font-mono">
                    {activeJob.avg_seconds_per_doc ? activeJob.avg_seconds_per_doc.toFixed(2) : '-'}s
                  </span>
                </div>
              </div>

              {/* Failure Breakdown if any */}
              {activeJob.error_summary && Object.keys(activeJob.error_summary).length > 0 && (
                <div className="pt-2 border-t border-slate-200 space-y-1">
                  <div className="text-3xs font-semibold text-rose-800 uppercase tracking-wider flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3 text-rose-600" />
                    Failures with Reasons:
                  </div>
                  {Object.entries(activeJob.error_summary).map(([reason, cnt]) => (
                    <div key={reason} className="text-3xs text-slate-600 flex justify-between bg-white px-2 py-1 rounded border border-slate-200">
                      <span className="truncate max-w-[200px]">{reason}</span>
                      <span className="font-mono font-bold text-rose-700">{cnt}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Card 2: Batch Analysis Runner */}
        <div className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-xs space-y-4">
          <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
            <Sparkles className="w-4 h-4 text-purple-600" />
            <h3 className="text-sm font-bold text-slate-900">2. Agentic Extraction & Verification</h3>
          </div>

          <p className="text-2xs text-slate-600 leading-relaxed">
            Segments operative sections of ingested orders, extracts directions with Gemini structured outputs, verifies verbatim source quotes, and computes deterministic deadline windows.
          </p>

          <div className="space-y-3">
            <div className="space-y-1">
              <label className="text-2xs font-bold uppercase tracking-wider text-slate-500">
                Batch Size (Unanalyzed Judgments)
              </label>
              <input
                type="number"
                min={1}
                max={50}
                value={analyzeLimit}
                onChange={(e) => setAnalyzeLimit(Number(e.target.value))}
                disabled={isAnalyzing}
                className="w-full text-xs rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 focus:outline-none focus:ring-1 focus:ring-slate-900"
              />
            </div>

            <button
              onClick={handleStartAnalysis}
              disabled={isAnalyzing}
              className={`w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg text-xs font-semibold text-white transition-all shadow-xs ${
                isAnalyzing
                  ? 'bg-purple-300 cursor-not-allowed'
                  : 'bg-purple-900 hover:bg-purple-800'
              }`}
            >
              {isAnalyzing ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Running LLM State Loop & Verifier...</span>
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5 fill-current" />
                  <span>Run Agentic Analysis Batch</span>
                </>
              )}
            </button>
          </div>

          {analyzeError && (
            <div className="rounded-lg bg-rose-50 border border-rose-200 p-3 text-2xs text-rose-700">
              {analyzeError}
            </div>
          )}

          {analyzeResult && (
            <div className="rounded-lg bg-purple-50/60 border border-purple-200 p-4 space-y-3">
              <div className="flex items-center justify-between text-2xs font-semibold text-purple-900">
                <span>Batch Analysis Completed</span>
                <span className="font-mono text-3xs bg-purple-100 text-purple-800 px-2 py-0.5 rounded">
                  {analyzeResult.average_latency_seconds}s avg latency
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center text-2xs">
                <div className="bg-white p-2 rounded border border-purple-100">
                  <span className="text-slate-400 block text-3xs">Orders</span>
                  <span className="font-bold text-slate-800 font-mono">{analyzeResult.total_judgments}</span>
                </div>
                <div className="bg-white p-2 rounded border border-purple-100">
                  <span className="text-slate-400 block text-3xs">With Directions</span>
                  <span className="font-bold text-purple-900 font-mono">{analyzeResult.judgments_with_directions}</span>
                </div>
                <div className="bg-white p-2 rounded border border-purple-100">
                  <span className="text-slate-400 block text-3xs">Total Directions</span>
                  <span className="font-bold text-slate-800 font-mono">{analyzeResult.total_directions}</span>
                </div>
                <div className="bg-white p-2 rounded border border-purple-100">
                  <span className="text-slate-400 block text-3xs">1st-Try Verified</span>
                  <span className="font-bold text-emerald-700 font-mono">{analyzeResult.verified_first_try_pct}%</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Real Ingested Judgments & Failure Reasons */}
      <div className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-xs space-y-3">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div>
            <h3 className="text-sm font-bold text-slate-900">Real Dataset Records (Live SQLite Inspection)</h3>
            <p className="text-2xs text-slate-500">
              Each document preserves real extraction status, text quality score, and verified failure reasons.
            </p>
          </div>
          <button
            onClick={fetchRecentDocs}
            className="text-slate-400 hover:text-slate-600 p-1.5 rounded hover:bg-slate-100"
            title="Refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingDocs ? 'animate-spin' : ''}`} />
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-100 text-left text-xs">
            <thead className="bg-slate-50 font-mono text-2xs uppercase tracking-wider text-slate-500">
              <tr>
                <th className="py-2.5 px-3">Case Number</th>
                <th className="py-2.5 px-3">Date</th>
                <th className="py-2.5 px-3">Court</th>
                <th className="py-2.5 px-3">Text Quality</th>
                <th className="py-2.5 px-3">Status</th>
                <th className="py-2.5 px-3">Reason / Error</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-mono text-2xs">
              {recentDocs.map((doc) => {
                const isFail = doc.status.includes('FAIL');
                const isAnalysed = doc.status === 'ANALYZED';

                return (
                  <tr key={doc.id} className="hover:bg-slate-50/80">
                    <td className="py-2.5 px-3 font-semibold text-slate-900">{doc.case_number}</td>
                    <td className="py-2.5 px-3 text-slate-600">{doc.judgment_date || '-'}</td>
                    <td className="py-2.5 px-3 text-slate-500">{doc.court}</td>
                    <td className="py-2.5 px-3">
                      {doc.text_quality !== undefined && doc.text_quality !== null ? (
                        <span
                          className={`px-1.5 py-0.5 rounded font-bold ${
                            doc.text_quality >= 0.8
                              ? 'bg-emerald-100 text-emerald-800'
                              : 'bg-amber-100 text-amber-800'
                          }`}
                        >
                          {(doc.text_quality * 100).toFixed(0)}%
                        </span>
                      ) : (
                        <span className="text-slate-400">-</span>
                      )}
                    </td>
                    <td className="py-2.5 px-3">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-3xs font-semibold ${
                          isAnalysed
                            ? 'bg-emerald-50 text-emerald-800 border border-emerald-300'
                            : isFail
                            ? 'bg-rose-50 text-rose-800 border border-rose-300'
                            : 'bg-slate-100 text-slate-800'
                        }`}
                      >
                        {isAnalysed && <CheckCircle2 className="w-3 h-3 text-emerald-600" />}
                        {isFail && <XCircle className="w-3 h-3 text-rose-600" />}
                        {doc.status}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-slate-500 max-w-xs truncate" title={doc.status}>
                      {isFail ? 'Marked FAILED_UNREADABLE (PyMuPDF unreadable)' : 'Clean extraction'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
