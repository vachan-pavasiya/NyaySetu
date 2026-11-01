import React, { useState, useEffect } from 'react';
import { Calendar as CalendarIcon, ChevronLeft, ChevronRight, RefreshCw, ExternalLink, ShieldCheck } from 'lucide-react';
import type { CalendarResponse, CalendarDirectionItem } from '../types';
import { StatusBadge, FlagBadges } from './StatusBadge';
import { getApiUrl } from '../config';

interface CalendarViewProps {
  onSelectJudgment?: (judgmentId: number) => void;
}

export const CalendarView: React.FC<CalendarViewProps> = ({ onSelectJudgment }) => {
  // Common months in dataset with deadline windows
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
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Header and Month Controls */}
      <div className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-xs flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <CalendarIcon className="w-5 h-5 text-slate-700" />
            <h2 className="text-lg font-bold text-slate-900 tracking-tight">Compliance Deadline Calendar</h2>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Deterministic deadline windows calculated per order ({data?.total_directions || 0} directions due in {currentMonth}).
          </p>
        </div>

        {/* Month Navigation */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg">
            <button
              onClick={() => changeMonth(-1)}
              className="p-1.5 rounded hover:bg-white text-slate-600 transition-colors"
              title="Previous Month"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <input
              type="month"
              value={currentMonth}
              onChange={(e) => e.target.value && setCurrentMonth(e.target.value)}
              className="text-xs font-mono font-semibold bg-transparent px-2 py-1 border-0 focus:ring-0 text-slate-800"
            />
            <button
              onClick={() => changeMonth(1)}
              className="p-1.5 rounded hover:bg-white text-slate-600 transition-colors"
              title="Next Month"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          {/* Quick Select Buttons */}
          <div className="hidden sm:flex items-center gap-1 text-2xs">
            <span className="text-slate-400 mr-1">Active:</span>
            {popularMonths.slice(0, 4).map((m) => (
              <button
                key={m}
                onClick={() => setCurrentMonth(m)}
                className={`px-2 py-1 rounded font-mono transition-colors ${
                  currentMonth === m
                    ? 'bg-slate-900 text-white font-bold'
                    : 'bg-slate-100 hover:bg-slate-200 text-slate-600'
                }`}
              >
                {m}
              </button>
            ))}
          </div>

          <button
            onClick={() => fetchCalendar(currentMonth)}
            className="p-2 text-slate-400 hover:text-slate-600 rounded-lg border border-slate-200 hover:bg-slate-50 transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Month Summary Cards */}
      {data && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-xs">
            <div className="text-2xs font-semibold uppercase tracking-wider text-slate-400">Total Due in Month</div>
            <div className="text-2xl font-black text-slate-900 mt-1 font-mono">{data.total_directions}</div>
          </div>
          <div className="rounded-xl border border-emerald-200/80 bg-emerald-50/40 p-4 shadow-xs">
            <div className="text-2xs font-semibold uppercase tracking-wider text-emerald-700">Complied</div>
            <div className="text-2xl font-black text-emerald-800 mt-1 font-mono">{data.status_summary.COMPLIED}</div>
          </div>
          <div className="rounded-xl border border-amber-200/80 bg-amber-50/40 p-4 shadow-xs">
            <div className="text-2xs font-semibold uppercase tracking-wider text-amber-700">Pending Process</div>
            <div className="text-2xl font-black text-amber-800 mt-1 font-mono">{data.status_summary.PENDING}</div>
          </div>
          <div className="rounded-xl border border-slate-200/80 bg-slate-50/60 p-4 shadow-xs">
            <div className="text-2xs font-semibold uppercase tracking-wider text-slate-600">Unverified Record</div>
            <div className="text-2xl font-black text-slate-800 mt-1 font-mono">{data.status_summary.UNVERIFIED}</div>
          </div>
        </div>
      )}

      {/* Directions List View */}
      {loading ? (
        <div className="rounded-xl border border-slate-200 bg-white py-24 text-center text-slate-400 text-xs">
          <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-slate-400" />
          Loading compliance deadlines for {currentMonth}...
        </div>
      ) : error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-6 text-center text-rose-700 text-xs">
          {error}
        </div>
      ) : data?.directions.length === 0 ? (
        <div className="rounded-xl border border-slate-200 bg-white p-12 text-center text-slate-400 text-xs italic">
          No compliance deadlines fall within {currentMonth}.
        </div>
      ) : (
        <div className="space-y-3">
          {data?.directions.map((d: CalendarDirectionItem) => (
            <div
              key={d.id}
              className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-xs hover:border-slate-300 transition-all flex flex-col md:flex-row md:items-center justify-between gap-4"
            >
              {/* Left Column: Date & Department Info */}
              <div className="space-y-1.5 md:max-w-md">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs font-bold px-2.5 py-0.5 rounded bg-slate-100 text-slate-900 border border-slate-200">
                    Window End: {d.deadline_window_end}
                  </span>
                  <span
                    className="font-mono text-2xs font-semibold text-slate-600 hover:text-slate-900 cursor-pointer"
                    onClick={() => onSelectJudgment && onSelectJudgment(d.judgment_id)}
                  >
                    {d.case_number || `Judgment #${d.judgment_id}`}
                  </span>
                </div>

                <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-900">
                  <span>{d.cleaned_department}</span>
                  {d.responsible_party !== d.cleaned_department && (
                    <span className="text-3xs text-slate-400 font-normal truncate max-w-[200px]" title={d.responsible_party}>
                      ({d.responsible_party})
                    </span>
                  )}
                </div>

                <p className="text-2xs text-slate-600 line-clamp-2 leading-relaxed">
                  {d.action}
                </p>

                {d.explanation_text && (
                  <div className="text-3xs text-slate-400 italic">
                    {d.explanation_text}
                  </div>
                )}
              </div>

              {/* Right Column: Status & Navigation */}
              <div className="flex flex-row md:flex-col items-end justify-between md:justify-center gap-2 shrink-0">
                <div className="flex items-center gap-1.5">
                  <StatusBadge status={d.compliance_status} size="sm" />
                  <FlagBadges flags={d.flags || {}} />
                </div>

                {d.evidence_strength && (
                  <span className="text-3xs px-2 py-0.5 rounded bg-slate-100 font-mono text-slate-600 flex items-center gap-1">
                    <ShieldCheck className="w-3 h-3 text-slate-500" />
                    {d.evidence_strength}
                  </span>
                )}

                <button
                  onClick={() => onSelectJudgment && onSelectJudgment(d.judgment_id)}
                  className="inline-flex items-center gap-1 text-2xs font-semibold text-blue-600 hover:text-blue-800 hover:underline pt-1"
                >
                  <span>View Order</span>
                  <ExternalLink className="w-3 h-3" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

