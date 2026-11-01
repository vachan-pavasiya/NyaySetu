import React, { useState, useEffect } from 'react';
import { ShieldCheck, AlertCircle, RefreshCw } from 'lucide-react';
import type { TimelineEvent } from '../types';

interface TimelineViewProps {
  initialCaseNumber?: string;
  onSelectJudgment?: (judgmentId: number) => void;
}

export const TimelineView: React.FC<TimelineViewProps> = ({ initialCaseNumber, onSelectJudgment }) => {
  // Common cases with linked proceedings in our database
  const sampleCases = [
    { caseNo: 'MAT/408/2022', label: 'MAT 408 of 2022 (Linked: CPAN 886 of 2022)' },
    { caseNo: 'FMA/1879/2019', label: 'FMA 1879 of 2019 (Linked: CPAN 1261 of 2019)' },
    { caseNo: 'WPA/2222/2022', label: 'WPA 2222 of 2022 (Linked: CPAN 1262 of 2022)' },
    { caseNo: 'WPA/5477/2022', label: 'WPA 5477 of 2022 (Linked: CPAN 1263 of 2022)' },
    { caseNo: 'WPA/7971/2021', label: 'WPA 7971 of 2021 (Linked: CPAN 926 of 2022)' },
    { caseNo: 'WPA/17378/2022', label: 'WPA 17378 of 2022 (Linked: CPAN 810 of 2023)' },
    { caseNo: 'WPA/4466/2022', label: 'WPA 4466 of 2022 (Linked: CPAN 446 of 2023)' },
    { caseNo: 'WPA/18860/2021', label: 'WPA 18860 of 2021 (Linked: CPAN 222 of 2023)' },
  ];

  const [selectedCase, setSelectedCase] = useState<string>(initialCaseNumber || sampleCases[0].caseNo);
  const [timelineData, setTimelineData] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initialCaseNumber) {
      setSelectedCase(initialCaseNumber);
    }
  }, [initialCaseNumber]);

  const fetchTimeline = async (caseNumber: string) => {
    setLoading(true);
    setError(null);
    try {
      const encoded = encodeURIComponent(caseNumber);
      let res = await fetch(`/api/cases/${encoded}/timeline`);
      if (!res.ok) {
        res = await fetch(`http://127.0.0.1:8000/cases/${encoded}/timeline`);
      }
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data = await res.json();
      setTimelineData(data);
    } catch (err: any) {
      console.error('Failed to fetch timeline:', err);
      setError(err.message || 'Failed to load case timeline');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTimeline(selectedCase);
  }, [selectedCase]);

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Case Selector Header */}
      <div className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-xs flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900 tracking-tight">Case Compliance Timeline</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Chronological audit of original court directions linked to subsequent contempt and compliance orders.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <label className="text-xs font-semibold text-slate-600">Select Case:</label>
          <select
            value={selectedCase}
            onChange={(e) => setSelectedCase(e.target.value)}
            className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-800 focus:bg-white focus:outline-none"
          >
            {!sampleCases.some((c) => c.caseNo === selectedCase) && (
              <option value={selectedCase}>{selectedCase}</option>
            )}
            {sampleCases.map((c) => (
              <option key={c.caseNo} value={c.caseNo}>
                {c.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Timeline Flow */}
      {loading ? (
        <div className="rounded-xl border border-slate-200 bg-white py-24 text-center text-slate-400 text-xs">
          <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2" />
          Building case compliance timeline...
        </div>
      ) : error ? (
        <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-rose-600 text-xs">
          <AlertCircle className="w-6 h-6 mx-auto mb-2" />
          {error}
        </div>
      ) : timelineData ? (
        <div className="space-y-6">
          {/* Case Metadata Banner */}
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs flex flex-wrap items-center justify-between gap-3 text-xs">
            <div>
              <span className="font-semibold text-slate-900 font-mono text-sm">{timelineData.case_number}</span>
              <span className="text-slate-500 ml-2">({timelineData.events?.length || 0} chronological events)</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-2xs px-2.5 py-1 rounded bg-slate-100 font-mono text-slate-700">
                CNR: {timelineData.cnr || 'N/A'}
              </span>
            </div>
          </div>

          {/* Timeline Cards */}
          <div className="relative pl-6 border-l-2 border-slate-200 space-y-8 ml-4">
            {timelineData.events?.map((ev: TimelineEvent, idx: number) => {
              const isLaterOrder = ev.event_type.includes('CONTEMPT') || ev.event_type.includes('FOLLOW_UP');
              const isOrig = ev.event_type.includes('ORIGINAL');

              return (
                <div key={idx} className="relative group">
                  {/* Timeline Dot */}
                  <div
                    className={`absolute -left-[31px] top-1.5 w-4 h-4 rounded-full border-2 bg-white flex items-center justify-center ${
                      isLaterOrder
                        ? 'border-purple-600 ring-4 ring-purple-100'
                        : isOrig
                        ? 'border-slate-900 ring-4 ring-slate-100'
                        : 'border-slate-400'
                    }`}
                  />

                  {/* Event Card */}
                  <div className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-xs space-y-3">
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2.5">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-xs text-slate-900">
                          {ev.case_number || timelineData.case_number}
                        </span>
                        <span className="text-2xs font-medium px-2 py-0.5 rounded bg-slate-100 text-slate-700">
                          {ev.event_type.replace('_', ' ')}
                        </span>
                      </div>
                      <span className="font-mono text-2xs text-slate-400">
                        {ev.date || 'Date unspecified'}
                      </span>
                    </div>

                    <div className="text-xs text-slate-800 leading-relaxed font-medium">
                      {ev.title}
                    </div>

                    <p className="text-xs text-slate-600 leading-normal">
                      {ev.description}
                    </p>

                    {/* Verified Quote / Evidence on later order */}
                    {ev.verified_quote && (
                      <div className="pt-2 border-t border-slate-100">
                        <div className="rounded-lg bg-emerald-50/70 border border-emerald-200/70 p-4 space-y-2">
                          <div className="flex items-center justify-between text-2xs">
                            <span className="font-semibold text-emerald-800 uppercase tracking-wider">
                              Verified Compliance Evidence
                            </span>
                            <span className="inline-flex items-center gap-1 font-semibold text-emerald-700 bg-emerald-100/70 px-2 py-0.5 rounded border border-emerald-300">
                              <ShieldCheck className="w-3 h-3" />
                              VERBATIM SUBSTRING
                            </span>
                          </div>
                          <div className="font-serif text-xs text-slate-800 italic leading-relaxed">
                            &ldquo;{ev.verified_quote}&rdquo;
                          </div>
                        </div>
                      </div>
                    )}
                    {/* Event Actions */}
                    {ev.judgment_id && onSelectJudgment && (
                      <div className="pt-2 flex justify-end">
                        <button
                          onClick={() => onSelectJudgment(ev.judgment_id!)}
                          className="text-3xs font-semibold text-blue-600 hover:text-blue-800 hover:underline"
                        >
                          View Judgment & Directions →
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
};
