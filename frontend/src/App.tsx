import { useState } from 'react';
import {
  Scale,
  LayoutDashboard,
  FileText,
  BookOpen,
  Clock,
  Calendar,
  DownloadCloud,
  FileCheck,
  AlertCircle,
  HelpCircle,
} from 'lucide-react';
import { DashboardView } from './components/DashboardView';
import { LedgerView } from './components/LedgerView';
import { JudgmentView } from './components/JudgmentView';
import { TimelineView } from './components/TimelineView';
import { CalendarView } from './components/CalendarView';
import { IngestView } from './components/IngestView';
import { EvalView } from './components/EvalView';

type Tab = 'dashboard' | 'ledger' | 'judgments' | 'timeline' | 'calendar' | 'ingest' | 'eval';

export function App() {
  const [activeTab, setActiveTab] = useState<Tab>('dashboard');

  // Cross-tab navigation state
  const [ledgerDepartment, setLedgerDepartment] = useState<string | undefined>(undefined);
  const [selectedJudgmentId, setSelectedJudgmentId] = useState<number | undefined>(undefined);
  const [selectedCaseNumber, setSelectedCaseNumber] = useState<string | undefined>(undefined);

  // Global "Why UNVERIFIED?" modal state
  const [showUnverifiedModal, setShowUnverifiedModal] = useState<boolean>(false);

  // Handlers for cross-tab linking
  const handleSelectDepartmentFromDashboard = (dept: string) => {
    setLedgerDepartment(dept);
    setActiveTab('ledger');
  };

  const handleSelectJudgment = (judgmentId: number) => {
    setSelectedJudgmentId(judgmentId);
    setActiveTab('judgments');
  };

  const handleSelectCaseFromLedger = (caseNumber: string) => {
    setSelectedCaseNumber(caseNumber);
    setActiveTab('timeline');
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-sans">
      {/* Top Header & Navigation */}
      <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/95 backdrop-blur-sm shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex h-16 items-center justify-between">
            {/* Logo */}
            <div
              className="flex items-center gap-3 cursor-pointer"
              onClick={() => setActiveTab('dashboard')}
            >
              <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-slate-900 text-white shadow-xs">
                <Scale className="w-5 h-5 text-emerald-400" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-extrabold text-base tracking-tight text-slate-900">NyaySetu</span>
                  <span className="text-2xs font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-200">
                    Live Radar
                  </span>
                </div>
                <div className="text-2xs text-slate-500 font-medium">Court-Order Compliance Radar</div>
              </div>
            </div>

            {/* Navigation Tabs */}
            <nav className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl overflow-x-auto">
              <button
                onClick={() => setActiveTab('dashboard')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all shrink-0 ${
                  activeTab === 'dashboard'
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <LayoutDashboard className="w-3.5 h-3.5" />
                <span>Dashboard</span>
              </button>

              <button
                onClick={() => {
                  setLedgerDepartment(undefined);
                  setActiveTab('ledger');
                }}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all shrink-0 ${
                  activeTab === 'ledger'
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <FileText className="w-3.5 h-3.5" />
                <span>Compliance Ledger</span>
              </button>

              <button
                onClick={() => setActiveTab('judgments')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all shrink-0 ${
                  activeTab === 'judgments'
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <BookOpen className="w-3.5 h-3.5" />
                <span>Judgment Verification</span>
              </button>

              <button
                onClick={() => setActiveTab('timeline')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all shrink-0 ${
                  activeTab === 'timeline'
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <Clock className="w-3.5 h-3.5" />
                <span>Case Timeline</span>
              </button>

              <button
                onClick={() => setActiveTab('calendar')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all shrink-0 ${
                  activeTab === 'calendar'
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <Calendar className="w-3.5 h-3.5" />
                <span>Calendar</span>
              </button>

              <button
                onClick={() => setActiveTab('ingest')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all shrink-0 ${
                  activeTab === 'ingest'
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <DownloadCloud className="w-3.5 h-3.5" />
                <span>Live Pipeline</span>
              </button>

              <button
                onClick={() => setActiveTab('eval')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all shrink-0 ${
                  activeTab === 'eval'
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <FileCheck className="w-3.5 h-3.5" />
                <span>Eval Harness</span>
              </button>
            </nav>
          </div>
        </div>

        {/* Legal Guardrail Banner (per AGENTS.md requirement) */}
        <div className="bg-amber-50/90 border-t border-b border-amber-200/80 px-4 py-1 text-center text-3xs font-medium text-amber-900 flex items-center justify-center gap-2">
          <AlertCircle className="w-3 h-3 text-amber-700 shrink-0" />
          <span>
            <strong>Legal Information, Not Legal Advice.</strong> All records are derived from official High Court open data (AWS CC-BY-4.0). Statuses require verified verbatim quotes.
          </span>
          <button
            onClick={() => setShowUnverifiedModal(true)}
            className="inline-flex items-center gap-0.5 text-amber-950 font-bold underline hover:text-amber-800 ml-2"
          >
            <HelpCircle className="w-2.5 h-2.5" />
            <span>Why UNVERIFIED?</span>
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {activeTab === 'dashboard' && (
          <DashboardView
            onSelectDepartment={handleSelectDepartmentFromDashboard}
            onSelectJudgment={handleSelectJudgment}
          />
        )}

        {activeTab === 'ledger' && (
          <LedgerView
            initialDepartment={ledgerDepartment}
            onSelectJudgment={handleSelectJudgment}
            onSelectCase={handleSelectCaseFromLedger}
          />
        )}

        {activeTab === 'judgments' && (
          <JudgmentView initialJudgmentId={selectedJudgmentId} />
        )}

        {activeTab === 'timeline' && (
          <TimelineView
            initialCaseNumber={selectedCaseNumber}
            onSelectJudgment={handleSelectJudgment}
          />
        )}

        {activeTab === 'calendar' && (
          <CalendarView onSelectJudgment={handleSelectJudgment} />
        )}

        {activeTab === 'ingest' && <IngestView />}

        {activeTab === 'eval' && <EvalView />}
      </main>

      {/* Global "Why UNVERIFIED?" Modal */}
      {showUnverifiedModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4">
          <div className="bg-white rounded-xl max-w-lg w-full p-6 shadow-xl border border-slate-200 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-slate-700" />
                <h3 className="font-bold text-sm text-slate-900">Why are most orders marked UNVERIFIED?</h3>
              </div>
              <button
                onClick={() => setShowUnverifiedModal(false)}
                className="text-slate-400 hover:text-slate-600 text-xs font-mono font-bold"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-xs text-slate-700 leading-relaxed">
              <p>
                In strict compliance with our legal guardrails, <strong>NyaySetu never infers compliance from silence</strong>.
              </p>
              <ul className="list-disc pl-5 space-y-1.5 text-2xs text-slate-600">
                <li>
                  <strong className="text-slate-900">COMPLIED</strong> is assigned <em>only</em> when a linked subsequent court order contains a verbatim, verified quote confirming compliance.
                </li>
                <li>
                  <strong className="text-slate-900">PENDING</strong> is assigned when the deterministic deadline window remains open, or a later order shows an ongoing process (e.g. extension sought, compliance report awaited).
                </li>
                <li>
                  <strong className="text-slate-900">UNVERIFIED</strong> indicates that the public repository does not contain subsequent proceedings for that case. If the deadline window has elapsed without record, the secondary flag <span className="font-mono text-3xs font-semibold bg-rose-50 text-rose-800 px-1 py-0.5 rounded">OVERDUE_NO_RECORD</span> is attached.
                </li>
              </ul>
              <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 text-3xs font-mono text-slate-600">
                Rule: UNVERIFIED means absence of subsequent public court orders, NOT non-compliance.
              </div>
            </div>

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setShowUnverifiedModal(false)}
                className="px-4 py-1.5 rounded-lg bg-slate-900 text-white text-xs font-semibold hover:bg-slate-800 transition-colors"
              >
                Understood
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <footer className="border-t border-slate-200 bg-white py-4 mt-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-2 text-2xs text-slate-500">
          <div>
            NyaySetu: Court-Order Compliance Radar • Live Open Data (AWS Indian High Court Judgments)
          </div>
          <div className="font-mono text-3xs text-slate-400">
            Headline Statuses: COMPLIED • PENDING • UNVERIFIED
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;
