import { useState, useEffect } from 'react';
import { DashboardView } from './components/DashboardView';
import { LedgerView } from './components/LedgerView';
import { JudgmentView } from './components/JudgmentView';
import { TimelineView } from './components/TimelineView';
import { CalendarView } from './components/CalendarView';
import { IngestView } from './components/IngestView';
import { EvalView } from './components/EvalView';
import { DiagnosticsView } from './components/DiagnosticsView';
import { NotFoundView } from './components/NotFoundView';
import { Logo } from './components/primitives/Logo';

type Tab =
  | 'dashboard'
  | 'ledger'
  | 'judgments'
  | 'timeline'
  | 'calendar'
  | 'ingest'
  | 'eval'
  | 'diagnostics'
  | '404';

interface NavItem {
  id: Tab;
  label: string;
  section: string;
}

const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', label: 'Principal Register', section: 'REGISTERS' },
  { id: 'ledger', label: 'Compliance Ledger', section: 'REGISTERS' },
  { id: 'judgments', label: 'Law Report & Judgments', section: 'PROCEEDINGS' },
  { id: 'timeline', label: 'Case Progression', section: 'PROCEEDINGS' },
  { id: 'calendar', label: 'Deadline Calendar', section: 'PROCEEDINGS' },
  { id: 'ingest', label: 'Data Pipeline & Ingest', section: 'DATA SYSTEM' },
  { id: 'eval', label: 'Evaluation Benchmarks', section: 'DATA SYSTEM' },
  { id: 'diagnostics', label: 'System Diagnostics', section: 'DATA SYSTEM' },
];

export function App() {
  const [activeTab, setActiveTab] = useState<Tab>('dashboard');
  const [isDark, setIsDark] = useState<boolean>(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState<boolean>(false);

  // Cross-tab navigation state
  const [ledgerDepartment, setLedgerDepartment] = useState<string | undefined>(undefined);
  const [selectedJudgmentId, setSelectedJudgmentId] = useState<number | undefined>(undefined);
  const [selectedCaseNumber, setSelectedCaseNumber] = useState<string | undefined>(undefined);

  // Global "Why UNVERIFIED?" modal state
  const [showUnverifiedModal, setShowUnverifiedModal] = useState<boolean>(false);

  // Synchronize document theme class
  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
      document.documentElement.setAttribute('data-theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      document.documentElement.removeAttribute('data-theme');
    }
  }, [isDark]);

  // Synchronize page titles
  useEffect(() => {
    const titles: Record<Tab, string> = {
      dashboard: 'NyaySetu — Principal Register of Compliance',
      ledger: 'NyaySetu — Compliance Ledger',
      judgments: 'NyaySetu — Law Report & Judgments',
      timeline: 'NyaySetu — Case Timeline Progression',
      calendar: 'NyaySetu — Compliance Deadline Calendar',
      ingest: 'NyaySetu — Data Pipeline & Ingestion',
      eval: 'NyaySetu — Evaluation Benchmarks',
      diagnostics: 'NyaySetu — System Diagnostics',
      '404': 'NyaySetu — Record Not Found',
    };
    document.title = titles[activeTab] || 'NyaySetu — Court-Order Compliance Radar';
  }, [activeTab]);

  // Handlers for cross-tab linking
  const handleSelectDepartmentFromDashboard = (dept: string) => {
    setLedgerDepartment(dept);
    setActiveTab('ledger');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleSelectJudgment = (judgmentId: number) => {
    setSelectedJudgmentId(judgmentId);
    setActiveTab('judgments');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleSelectCaseFromLedger = (caseNumber: string) => {
    setSelectedCaseNumber(caseNumber);
    setActiveTab('timeline');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div className="min-h-screen bg-[var(--bg-paper)] text-[var(--ink-primary)] flex flex-col font-sans transition-colors duration-150">
      {/* Top Gazette Notice Strip */}
      <aside
        aria-label="Official Legal Information Notice"
        className="masthead-banner border-b border-[var(--border-rule-strong)] bg-[var(--bg-surface-muted)] text-[var(--ink-secondary)] text-[11px] font-mono py-1 px-4 text-center select-none flex items-center justify-center gap-2 flex-wrap"
      >
        <span>
          <strong>Gazette Notice:</strong> Legal information, not legal advice. Operative records derived from official High Court open data (AWS CC-BY-4.0).
        </span>
        <button
          onClick={() => setShowUnverifiedModal(true)}
          className="text-[var(--accent-oxblood)] font-bold underline hover:opacity-80 transition-opacity ml-1"
        >
          Why UNVERIFIED?
        </button>
      </aside>

      {/* Masthead Header Bar */}
      <header className="border-b border-[var(--border-rule)] bg-[var(--bg-surface)] sticky top-0 z-30">
        <div className="w-full px-4 sm:px-6 py-2.5 flex items-center justify-between">
          {/* Logo & Gazette Title */}
          <div
            className="cursor-pointer"
            onClick={() => {
              setActiveTab('dashboard');
              setMobileMenuOpen(false);
            }}
          >
            <Logo size="md" />
          </div>

          {/* Right Toolbar: Jurisdiction & Theme Toggle */}
          <div className="flex items-center gap-3">
            <div className="hidden lg:flex flex-col text-right font-mono text-[10px] text-[var(--ink-secondary)]">
              <span className="font-semibold text-[var(--ink-primary)]">Calcutta High Court</span>
              <span>Appellate Side · 2023 Records</span>
            </div>

            <div className="h-5 w-[1px] bg-[var(--border-rule)] hidden lg:block" />

            {/* Dark / Light Toggle in Warm Charcoal */}
            <button
              onClick={() => setIsDark(!isDark)}
              className="font-mono text-[11px] uppercase tracking-wider px-2 py-1 border border-[var(--border-rule-strong)] rounded-[2px] hover:bg-[var(--bg-surface-muted)] transition-colors"
              title="Toggle reading theme between paper and warm charcoal"
            >
              {isDark ? 'Paper (Light)' : 'Charcoal (Dark)'}
            </button>

            {/* Mobile menu button */}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="md:hidden font-mono text-xs px-2.5 py-1 border border-[var(--border-rule-strong)] rounded-[2px]"
            >
              {mobileMenuOpen ? 'Close' : 'Menu'}
            </button>
          </div>
        </div>

        {/* Mobile Navigation Dropdown (<768px) */}
        {mobileMenuOpen && (
          <nav className="md:hidden border-t border-[var(--border-rule)] bg-[var(--bg-surface)] p-2 grid grid-cols-2 gap-1 font-mono text-xs">
            {NAV_ITEMS.map((item) => (
              <button
                key={item.id}
                onClick={() => {
                  setActiveTab(item.id);
                  setMobileMenuOpen(false);
                }}
                className={`text-left px-2 py-1.5 border border-transparent rounded-[2px] ${
                  activeTab === item.id
                    ? 'border-[var(--accent-oxblood)] bg-[var(--bg-surface-muted)] text-[var(--accent-oxblood)] font-bold'
                    : 'text-[var(--ink-secondary)] hover:bg-[var(--bg-surface-muted)]'
                }`}
              >
                {item.label}
              </button>
            ))}
          </nav>
        )}
      </header>

      {/* Main Structural Frame: Fixed Left Rail + Editorial Content Area */}
      <div className="flex-1 flex flex-col md:flex-row w-full">
        {/* Fixed Left Rail Navigation (Desktop) */}
        <aside
          aria-label="Publication Navigation"
          className="hidden md:block w-56 shrink-0 border-r border-[var(--border-rule)] bg-[var(--bg-surface)] p-4 select-none min-h-[calc(100vh-80px)]"
        >
          <div className="sticky top-16 space-y-6">
            {['REGISTERS', 'PROCEEDINGS', 'DATA SYSTEM'].map((sectionName) => (
              <div key={sectionName} className="space-y-1.5">
                <div className="font-mono text-[9px] uppercase tracking-widest text-[var(--ink-muted)] font-semibold px-2">
                  {sectionName}
                </div>
                <div className="space-y-0.5">
                  {NAV_ITEMS.filter((item) => item.section === sectionName).map((item) => {
                    const isActive = activeTab === item.id;
                    return (
                      <button
                        key={item.id}
                        onClick={() => {
                          if (item.id === 'ledger') setLedgerDepartment(undefined);
                          setActiveTab(item.id);
                        }}
                        className={`w-full text-left px-2.5 py-1.5 font-sans text-xs transition-colors rounded-[2px] block ${
                          isActive
                            ? 'border-l-2 border-[var(--accent-oxblood)] bg-[var(--bg-surface-muted)] text-[var(--accent-oxblood)] font-bold'
                            : 'text-[var(--ink-secondary)] hover:text-[var(--ink-primary)] hover:bg-[var(--bg-surface-muted)]'
                        }`}
                      >
                        {item.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}

            <div className="pt-6 border-t border-[var(--border-rule)] font-mono text-[10px] text-[var(--ink-muted)] space-y-1">
              <div>AWS S3: indian-high-court-judgments</div>
              <div>License: CC-BY-4.0 Public</div>
            </div>
          </div>
        </aside>

        {/* Editorial Content Canvas */}
        <main className="flex-1 w-full max-w-6xl mx-auto p-4 sm:p-6 lg:p-8">
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

          {activeTab === 'diagnostics' && <DiagnosticsView />}

          {activeTab === '404' && (
            <NotFoundView onReturnToDashboard={() => setActiveTab('dashboard')} />
          )}
        </main>
      </div>

      {/* Global "Why UNVERIFIED?" Modal */}
      {showUnverifiedModal && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
        >
          <div className="bg-[var(--bg-surface)] border border-[var(--border-rule-strong)] max-w-lg w-full p-5 space-y-3 rounded-[2px]">
            <div className="flex items-baseline justify-between border-b border-[var(--border-rule)] pb-2">
              <h2 className="font-serif font-bold text-base text-[var(--ink-primary)]">
                The Ground-Truth Standard: Why UNVERIFIED?
              </h2>
              <button
                onClick={() => setShowUnverifiedModal(false)}
                className="font-mono text-xs text-[var(--ink-muted)] hover:text-[var(--ink-primary)] font-bold"
              >
                [X]
              </button>
            </div>

            <div className="space-y-2.5 font-sans text-xs text-[var(--ink-secondary)] leading-relaxed">
              <p className="font-semibold text-[var(--ink-primary)]">
                UNVERIFIED means we found no public record either way. It does not mean the order was ignored.
              </p>
              <p>
                In strict compliance with our legal guardrails, <strong>NyaySetu never infers compliance from silence</strong>. High Court registries do not automatically link post-judgment department actions back into the initial order docket.
              </p>
              <ul className="list-disc pl-5 space-y-1.5 text-[11px]">
                <li>
                  <strong className="text-[var(--ink-primary)]">COMPLIED</strong> is assigned <em>only</em> when a linked subsequent order contains a verified, verbatim judicial quote confirming execution.
                </li>
                <li>
                  <strong className="text-[var(--ink-primary)]">PENDING</strong> is assigned when the deterministic deadline window remains open, or a subsequent order records an ongoing administrative step (e.g. extension sought, compliance report awaited).
                </li>
                <li>
                  <strong className="text-[var(--ink-primary)]">UNVERIFIED</strong> indicates absence of subsequent public proceedings. If the deadline window has elapsed without record, the flag <code className="font-mono text-[10px] text-[var(--status-overdue)]">OVERDUE_NO_RECORD</code> is attached.
                </li>
              </ul>
              <div className="border border-[var(--border-rule)] bg-[var(--bg-paper)] p-2.5 font-mono text-[10px] text-[var(--ink-muted)]">
                Rule: Legal information, not legal advice. Everything is derived from official open records.
              </div>
            </div>

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setShowUnverifiedModal(false)}
                className="font-mono text-xs uppercase tracking-wider font-semibold px-4 py-1.5 border border-[var(--ink-primary)] bg-[var(--ink-primary)] text-[var(--bg-paper)] hover:bg-[var(--accent-oxblood)] hover:border-[var(--accent-oxblood)] transition-colors rounded-[2px]"
              >
                Understood
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Gazette Footer */}
      <footer className="border-t border-[var(--border-rule)] bg-[var(--bg-surface)] py-3 select-none no-print">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 flex flex-col sm:flex-row items-center justify-between gap-2 font-mono text-[10px] text-[var(--ink-muted)]">
          <div>
            NyaySetu: Court-Order Compliance Radar · AWS Open Data (CC-BY-4.0)
          </div>
          <div>
            Headline Standards: COMPLIED · PENDING · UNVERIFIED
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;
