export interface EvidenceItem {
  id: number;
  source_case_number?: string;
  source_judgment_id?: number;
  source_date?: string;
  verdict: string;
  supporting_quote?: string;
  reasoning?: string;
  verified: boolean;
  evidence_strength?: 'COURT_RECORDED' | 'PARTY_SUBMISSION' | string;
  evidence_scope?: 'CASE_LEVEL' | 'DIRECTION_SPECIFIC' | string;
  directions_covered_count?: number;
  model_used?: string;
  method?: string;
  created_at?: string;
}

export interface DirectionItem {
  id: number;
  judgment_id: number;
  case_number?: string;
  judgment_date?: string;
  responsible_party: string;
  party_type: string;
  direction_type: string;
  action: string;
  deadline_phrase?: string;
  source_quote: string;
  anchor_type?: string;
  offset_value?: number;
  offset_unit?: string;
  deadline_window_start?: string;
  deadline_window_end?: string;
  deadline_status: string;
  compliance_status: 'COMPLIED' | 'PENDING' | 'UNVERIFIED';
  status: 'COMPLIED' | 'PENDING' | 'UNVERIFIED';
  sub_reason?: string;
  flags: {
    contempt_filed: boolean;
    extension_sought: boolean;
    overdue_no_record: boolean;
    contempt_dismissed_for_default: boolean;
  };
  explanation_text?: string;
  evidence_strength?: 'COURT_RECORDED' | 'PARTY_SUBMISSION' | string;
  evidence_scope?: 'CASE_LEVEL' | 'DIRECTION_SPECIFIC' | string;
  directions_covered_count?: number;
  evidence?: EvidenceItem[];
  created_at?: string;
}

export interface LedgerItem {
  id: number;
  direction_id: number;
  judgment_id: number;
  case_number?: string;
  court?: string;
  judgment_date?: string;
  responsible_party: string;
  cleaned_department?: string;
  party_type: string;
  direction_type: string;
  action: string;
  deadline_phrase?: string;
  deadline_window_start?: string;
  deadline_window_end?: string;
  deadline_status: string;
  explanation_text?: string;
  compliance_status: 'COMPLIED' | 'PENDING' | 'UNVERIFIED';
  status: 'COMPLIED' | 'PENDING' | 'UNVERIFIED';
  sub_reason?: string;
  flags: {
    contempt_filed: boolean;
    extension_sought: boolean;
    overdue_no_record: boolean;
    contempt_dismissed_for_default: boolean;
  };
  evidence_strength?: string;
  evidence_scope?: string;
  directions_covered_count?: number;
  primary_quote?: string;
  primary_verdict?: string;
  primary_case?: string;
  evidence_count: number;
  judgment_link?: string;
}

export interface LedgerResponse {
  total: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
  limit: number;
  offset: number;
  items: LedgerItem[];
}

export interface DepartmentSummary {
  department: string;
  total: number;
  complied: number;
  pending: number;
  unverified: number;
  overdue: number;
}

export interface OverallStats {
  total_judgments: number;
  total_directions: number;
  status_distribution: {
    COMPLIED: number;
    PENDING: number;
    UNVERIFIED: number;
  };
  flags_distribution: {
    overdue_no_record: number;
    contempt_filed: number;
    extension_sought: number;
    contempt_dismissed_for_default: number;
  };
  evidence_strength_distribution: {
    COURT_RECORDED: number;
    PARTY_SUBMISSION: number;
  };
  case_level_directions_count: number;
  top_departments: DepartmentSummary[];
}

export interface JudgmentSummary {
  id: number;
  court: string;
  year: number;
  case_number: string;
  cnr?: string;
  judgment_date?: string;
  petitioner?: string;
  respondent?: string;
  text_quality?: number;
  status: string;
}

export interface JudgmentDetail {
  id: number;
  court: string;
  year: number;
  case_number: string;
  cnr?: string;
  judgment_date?: string;
  petitioner?: string;
  respondent?: string;
  s3_key?: string;
  text?: string;
  text_quality?: number;
  status: string;
  error?: string;
  created_at: string;
}

export interface IngestJobResponse {
  job_id: string;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';
  court: string;
  year: number;
  limit: number;
  total: number;
  processed: number;
  succeeded: number;
  failed: number;
  avg_seconds_per_doc?: number;
  error_summary?: Record<string, number>;
  started_at: string;
  completed_at?: string;
}

export interface BatchAnalyzeResponse {
  total_judgments: number;
  judgments_with_directions: number;
  total_directions: number;
  verified_first_try_pct: number;
  verified_after_retry_pct: number;
  average_latency_seconds: number;
  results: any[];
}

export interface TimelineEvent {
  date?: string;
  event_type: string;
  title: string;
  description: string;
  case_number?: string;
  judgment_id?: number;
  verified_quote?: string;
  confidence?: number | string;
}

export interface AgentRunStep {
  step: string;
  status: string;
  duration_seconds: number;
  timestamp: string;
  details?: Record<string, any>;
}

export interface AgentRunItem {
  id: number;
  trigger: string;
  source_judgment_id?: number;
  source_case_number?: string;
  steps: AgentRunStep[];
  directions_checked_count: number;
  directions_updated_count: number;
  outcome: string;
  errors?: string;
  duration_seconds: number;
  created_at: string;
  message: string;
}

export interface AgentRunsResponse {
  total: number;
  runs: AgentRunItem[];
}

export interface DueDirectionItem {
  id: number;
  direction_id: number;
  case_number?: string;
  judgment_id: number;
  responsible_party: string;
  cleaned_department: string;
  action: string;
  deadline_window_end?: string;
  deadline_status: string;
  compliance_status: string;
  days_remaining?: number;
  sub_reason?: string;
  judgment_link: string;
}

export interface DashboardDepartmentSummary {
  department: string;
  total: number;
  open_count: number;
  complied: number;
  pending: number;
  unverified: number;
  overdue: number;
}

export interface DashboardResponse {
  status_counts: {
    COMPLIED: number;
    PENDING: number;
    UNVERIFIED: number;
  };
  overdue_no_record_count: number;
  contempt_filed_count: number;
  evidence_strength_split: {
    COURT_RECORDED: number;
    PARTY_SUBMISSION: number;
  };
  deadline_bucket_counts: Record<string, number>;
  top_departments: DashboardDepartmentSummary[];
  directions_due_next_30_days: DueDirectionItem[];
  due_next_30_days_count: number;
  dataset_freshness: {
    latest_judgment_date?: string;
    total_judgments: number;
    analysed_count: number;
  };
  link_stats: {
    total_links: number;
    by_type: Record<string, number>;
    by_signal: Record<string, number>;
    by_confidence: Record<string, number>;
  };
  recent_pipeline_runs: AgentRunItem[];
  disclaimer: string;
  unverified_note: string;
}

export interface CalendarDirectionItem {
  id: number;
  direction_id: number;
  judgment_id: number;
  case_number?: string;
  court?: string;
  judgment_date?: string;
  responsible_party: string;
  cleaned_department: string;
  action: string;
  deadline_phrase?: string;
  deadline_window_start?: string;
  deadline_window_end: string;
  deadline_status: string;
  compliance_status: 'COMPLIED' | 'PENDING' | 'UNVERIFIED';
  sub_reason?: string;
  flags: {
    contempt_filed: boolean;
    extension_sought: boolean;
    overdue_no_record: boolean;
    contempt_dismissed_for_default: boolean;
  };
  explanation_text?: string;
  evidence_strength?: string;
  evidence_scope?: string;
  judgment_link: string;
}

export interface CalendarResponse {
  month: string;
  total_directions: number;
  status_summary: {
    COMPLIED: number;
    PENDING: number;
    UNVERIFIED: number;
  };
  directions: CalendarDirectionItem[];
}

export interface EvalSummary {
  gold_files_count: number;
  overall_extraction_f1: number;
  overall_extraction_precision: number;
  overall_extraction_recall: number;
  hallucination_rate_pct: number;
  deadline_exact_accuracy_pct: number;
  deadline_cases_tested: number;
  linking_f1_pct: number;
  linking_precision_pct: number;
  linking_recall_pct: number;
  temporal_sanity_violations: number;
}

export interface EvalResultsResponse {
  timestamp: string;
  summary: EvalSummary;
  extraction: Record<string, any>;
  deadline_resolution: Record<string, any>;
  linking: Record<string, any>;
}

