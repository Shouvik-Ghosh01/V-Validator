export interface ClientMetadata {
  script_id: string;
  title: string;
  description: string;
  run_number?: string | number;
}

export interface ExecutedMetadata {
  script_id: string;
  title: string;
  description: string;
  start_time?: string;
  end_time?: string;
  script_run_time?: string;
}

export interface StepStats {
  total_steps: number;
  setup_steps?: number;
  execution_steps?: number;
  pre_test_setup_steps?: number;
}

export interface Statistics {
  client?: StepStats;
  executed?: StepStats;
}

export interface Summary {
  total_issues: number;
  setup_steps_with_issues: number;
  execution_steps_with_issues: number;
}

export interface SetupDifference {
  type: 'missing' | 'procedure_mismatch' | 'ensure_accounts_with_dynamic_data';
  message?: string;
  client?: string;
  executed?: string;
  accounts?: Record<string, string>;
}

export interface ExecutionDifference {
  type:
    | 'missing'
    | 'procedure_mismatch'
    | 'expected_mismatch'
    | 'expected_vs_actual_mismatch'
    | 'expected_with_dynamic_data';
  message?: string;
  client?: string;
  executed?: string;
  client_expected?: string;
  executed_actual?: string;
  expected?: string;
  actual?: string;
  dynamic_data?: Record<string, string>;
}

export interface ComparisonResult {
  has_differences: boolean;
  client_metadata: ClientMetadata;
  executed_metadata: ExecutedMetadata;
  statistics: Statistics;
  summary: Summary;
  setup_differences: Record<string, SetupDifference[]>;
  execution_differences: Record<string, ExecutionDifference[]>;
}
