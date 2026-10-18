export type JobKind = 'verify' | 'migrate' | 'build' | 'mutation'
export type JobStatus = 'queued' | 'running' | 'passed' | 'failed' | 'error' | 'cancelled'

export interface Job {
  id: string
  kind: JobKind
  params: Record<string, unknown>
  status: JobStatus
  created: number
  started: number | null
  finished: number | null
  result: Record<string, unknown>
  event_count: number
  owner: { project_id?: string | null; user_id?: string; user_name?: string; via?: string }
  pending_gate: Gate | null
}

export interface Attempt {
  label: string
  build: boolean
  scenarios_passed: number
  scenarios_total: number
  records_matched: number
  records_total: number
  prompt_tokens: number
  output_tokens: number
}

export interface Mismatch {
  key: string
  problem?: string
  diffs?: { field: string; expected: string; actual: string }[]
}
export interface ArtifactReport {
  artifact: string
  status: 'IDENTICAL' | 'MISMATCH' | 'MISSING'
  golden_records: number | null
  matched: number
  mismatch_count: number
  mismatches: Mismatch[]
}
export interface ScenarioResult {
  name: string
  program: string
  passed: boolean
  seconds: number
  records_matched: number
  records_total: number
  crashed: boolean
  console: string
  report: { artifacts?: ArtifactReport[]; return_code_matches?: boolean; counters_match?: boolean }
}

type Base = { seq: number; ts: number }
export type StudioEvent =
  | (Base & { type: 'log'; line: string })
  | (Base & { type: 'attempt' } & Attempt)
  | (Base & { type: 'plan'; scenarios: string[] })
  | (Base & { type: 'scenario_start'; name: string })
  | (Base & { type: 'scenario' } & ScenarioResult)
  | (Base & { type: 'status'; status: JobStatus; result?: Record<string, unknown> })
  | (Base & { type: 'step' } & StepEvent)
  | (Base & { type: 'gate' } & Gate)
  | (Base & { type: 'gate_done' } & GateDecision)

export interface EnvCheck { id: string; label: string; ok: boolean; detail: string }
export interface Program { id: string; cobol: string; title: string; package: string; summary: string }

export interface ScenarioInfo {
  name: string
  program: string
  artifacts: string[]
  case_count: number
  categories: Record<string, number>
  sample_cases: { key: string; label: string; category?: string }[]
  return_code: string | null
}

export interface RunSummary {
  id: string
  source: 'results' | 'runs'
  name: string
  created: string | null
  program: string
  provider: string
  model: string
  mode: string
  verdict: 'PASS' | 'FAIL'
  attempts: number
  repairs: number
  first_records_matched: number | null
  final_records_matched: number | null
  records_total: number | null
  prompt_tokens: number
  output_tokens: number
  llm_seconds: number
  is_mock: boolean
  project_id?: string | null
  started_by?: string | null
}
export interface RunIteration {
  iteration: number
  build: boolean
  prompt_tokens: number
  output_tokens: number
  llm_seconds?: number
  scenarios_passed?: number
  scenarios_total?: number
  records_matched?: number
  records_total?: number
  all_pass?: boolean
  build_error?: string
}
export interface RunDetail {
  summary: RunSummary
  report: { iterations: RunIteration[] }
  rules: unknown
  iterations_available: number[]
}
export interface IterationDetail { n: number; prompt: string; feedback: string; notes: string; files: Record<string, string> }

export interface GoldenPage {
  scenario: string
  artifact: string
  record_length: number
  total: number
  columns: string[]
  masked: string[]
  rows: { key: string; label: string | null; fields: Record<string, string> }[]
}
export interface SourceFile { path: string; content: string }
export interface CobolSource { available: boolean; program: string; content: string; copybooks: Record<string, string>; hint?: string }

// ---------------------------------------------------------------- auth, roles and administration
export type Role = 'project_admin' | 'lead_architect' | 'senior_dev' | 'junior_dev' | 'intern'
export interface User { id: string; email: string; name: string; role: Role; role_label?: string; active?: number }
export interface Policy {
  providers: string[]
  model_tier: 'none' | 'basic' | 'advanced'
  max_repairs: number
  modes: string[]
  agents: string[]
  can_approve_gates: boolean
  can_edit_board: boolean
  can_run_verifier: boolean
  can_run_mutation: boolean
  can_run_build: boolean
  runs_per_day: number
  daily_token_budget: number
}
export interface Project { id: string; name: string; description: string; token_budget: number | null }
export interface Budget { limit: number; used: number }
export interface Budgets { user: Budget; runs: Budget; teams: (Budget & { id: string; name: string })[]; project: (Budget & { id: string; name: string }) | null }
export interface ModelCfg { id: string; tier: 'basic' | 'advanced' }
export interface Profile {
  user: User
  policy: Policy
  agents: { id: string; label: string; allowed: boolean }[]
  projects: Project[]
  provider: { enabled: boolean; has_key: boolean; models: ModelCfg[]; default_model: string }
  budgets: Budgets
}

export interface AdminUser extends User { created: number; teams: string[]; projects: string[] }
export interface Team { id: string; name: string; daily_token_budget: number | null; members: string[] }
export interface AdminProject extends Project { users: string[]; teams: string[]; archived: number; tokens_used: number }
export interface ProviderCfg { enabled: boolean; models: ModelCfg[]; default_model: string; has_key: boolean; key_hint: string | null; updated: number | null }
export interface Usage {
  by_user: { name: string; role: Role; runs: number; tokens: number }[]
  by_project: { name: string; token_budget: number | null; runs: number; tokens: number }[]
  recent: { ts: number; user: string; project: string; provider: string; model: string | null; prompt_tokens: number; output_tokens: number }[]
}
export interface AuditRow { ts: number; user: string | null; action: string; detail: string }

// ---------------------------------------------------------------- migration steps, gates and the orchestration board
export type StepKind = 'llm' | 'build' | 'verify' | 'decision'
export interface StepEvent {
  kind: StepKind
  iteration: number
  state?: 'start' | 'done'
  ok?: boolean
  passed?: number
  total?: number
  records_matched?: number
  records_total?: number
  outcome?: 'pass' | 'mismatch' | 'build_failed' | 'exhausted'
  prompt_tokens?: number
  output_tokens?: number
}
export interface Gate { id: string; point: 'generate' | 'repair'; iteration: number; summary: string; detail: string; timeout: number }
export interface GateDecision { id: string; action: 'approve' | 'stop'; hint: string; by: string | null }

export interface BoardNode { id: string; type: string; position: { x: number; y: number }; data: Record<string, unknown> }
export interface BoardEdge { id: string; source: string; target: string; sourceHandle?: string | null; targetHandle?: string | null; label?: string }
export interface BoardGraph { nodes: BoardNode[]; edges: BoardEdge[] }
export interface Compiled { ok: boolean; errors: string[]; warnings: string[]; agents: string[]; params: Record<string, unknown> | null }
