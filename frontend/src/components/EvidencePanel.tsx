import React from 'react';
import { FileCheck, ShieldCheck, Scale, Users, Layers, Quote } from 'lucide-react';
import type { EvidenceItem } from '../types';

interface EvidencePanelProps {
  evidence: EvidenceItem[];
  title?: string;
}

export const EvidencePanel: React.FC<EvidencePanelProps> = ({ evidence, title = 'Verified Compliance Evidence' }) => {
  if (!evidence || evidence.length === 0) {
    return (
      <div className="rounded-lg border border-slate-200 bg-slate-50/70 p-4 text-xs text-slate-500 italic">
        No subsequent compliance order or evidence linked to this direction.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {title && (
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
          <FileCheck className="w-4 h-4 text-emerald-600" />
          <span>{title} ({evidence.length})</span>
        </div>
      )}

      {evidence.map((ev) => {
        const isCourt = ev.evidence_strength === 'COURT_RECORDED';
        const isCaseLevel = ev.evidence_scope === 'CASE_LEVEL';

        return (
          <div
            key={ev.id}
            className="rounded-lg border border-emerald-200/80 bg-white p-4 shadow-xs ring-1 ring-emerald-500/10 space-y-3"
          >
            {/* Header: Source Case & Meta */}
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2.5">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-sm text-slate-900">
                  {ev.source_case_number || 'Linked Follow-up Order'}
                </span>
                {ev.source_date && (
                  <span className="text-xs text-slate-500">
                    dated {ev.source_date}
                  </span>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-1.5">
                {/* Strength Badge */}
                {ev.evidence_strength && (
                  <span
                    className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-2xs font-medium border ${
                      isCourt
                        ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                        : 'bg-indigo-50 text-indigo-700 border-indigo-200'
                    }`}
                    title={
                      isCourt
                        ? 'Court itself judicially records or makes a finding of compliance'
                        : 'Counsel or party submits/states that compliance occurred'
                    }
                  >
                    {isCourt ? <Scale className="w-3 h-3 text-emerald-600" /> : <Users className="w-3 h-3 text-indigo-600" />}
                    <span>{ev.evidence_strength.replace('_', ' ')}</span>
                  </span>
                )}

                {/* Scope Badge */}
                {ev.evidence_scope && (
                  <span
                    className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-2xs font-medium border ${
                      isCaseLevel
                        ? 'bg-amber-50 text-amber-800 border-amber-200'
                        : 'bg-slate-50 text-slate-700 border-slate-200'
                    }`}
                    title={
                      isCaseLevel
                        ? `Order disposed at case level; covers ${ev.directions_covered_count || 'multiple'} directions in the matter`
                        : 'Order addresses this specific direction individually'
                    }
                  >
                    <Layers className="w-3 h-3 text-amber-600" />
                    <span>
                      {isCaseLevel
                        ? `CASE LEVEL (${ev.directions_covered_count || 'multi'} dirs)`
                        : 'DIRECTION SPECIFIC'}
                    </span>
                  </span>
                )}

                {/* Verifier Badge */}
                {ev.verified ? (
                  <span
                    className="inline-flex items-center gap-1 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 text-2xs font-semibold"
                    title="Exact verbatim substring verified in source High Court text"
                  >
                    <ShieldCheck className="w-3 h-3 text-emerald-600" />
                    <span>VERBATIM VERIFIED</span>
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-md bg-rose-50 text-rose-700 border border-rose-200 px-2 py-0.5 text-2xs">
                    Unverified Quote
                  </span>
                )}
              </div>
            </div>

            {/* Verbatim Supporting Quote */}
            {ev.supporting_quote && (
              <div className="relative rounded-md bg-emerald-50/50 border border-emerald-200/60 p-3 pl-8 text-xs text-slate-800 leading-relaxed font-serif">
                <Quote className="w-4 h-4 text-emerald-500/70 absolute left-2.5 top-3" />
                <span>&ldquo;{ev.supporting_quote}&rdquo;</span>
              </div>
            )}

            {/* Verdict & Reasoning */}
            <div className="space-y-1 text-xs">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-slate-700">Verdict:</span>
                <span className="font-mono text-2xs bg-slate-100 text-slate-800 px-1.5 py-0.5 rounded border border-slate-200">
                  {ev.verdict}
                </span>
              </div>
              {ev.reasoning && (
                <p className="text-slate-600 text-xs leading-normal">
                  <span className="font-medium text-slate-700">Reasoning: </span>
                  {ev.reasoning}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};
