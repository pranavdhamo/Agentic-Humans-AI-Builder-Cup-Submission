import type {
  AdminProject, AdminUser, AuditRow, BoardGraph, Budgets, CobolSource, Compiled, EnvCheck, GoldenPage, IterationDetail, Job, Policy,
  Profile, Program, ProviderCfg, RunDetail, RunSummary, ScenarioInfo, SourceFile, Team, Usage,
} from './types'

const BASE = import.meta.env.VITE_API_BASE ?? ''
const TOKEN_KEY = 'studio-token'

export const tokenStore = {
  get: (): string | null => { try { return localStorage.getItem(TOKEN_KEY) } catch { return null } },
  set: (t: string) => { try { localStorage.setItem(TOKEN_KEY, t) } catch { /* private mode */ } },
  clear: () => { try { localStorage.removeItem(TOKEN_KEY) } catch { /* private mode */ } },
}

let onUnauthorized: () => void = () => undefined
export const setUnauthorizedHandler = (fn: () => void) => { onUnauthorized = fn }

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = tokenStore.get()
  const headers: Record<string, string> = {}
  if (init.body) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(`${BASE}${path}`, { ...init, headers })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const j = await res.json()
      detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch { /* keep the status text */ }
    if (res.status === 401 && token) onUnauthorized()
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

const send = <T>(method: string, path: string, body?: unknown) => req<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) })

export interface MigrateRequest {
  project_id: string; program: string; provider: string; mode: string; max_repairs: number; model?: string; gates?: string[]
}

export const api = {
  // auth
  login: (email: string, password: string) => send<Profile & { token: string }>('POST', '/api/auth/login', { email, password }),
  me: () => req<Profile>('/api/auth/me'),
  changePassword: (current: string, next: string) => send<{ ok: boolean }>('POST', '/api/auth/password', { current, new: next }),
  health: () => req<{ status: string; version: string }>('/api/health'),

  // catalog
  environment: () => req<{ checks: EnvCheck[] }>('/api/environment'),
  programs: () => req<Program[]>('/api/programs'),
  scenarios: () => req<ScenarioInfo[]>('/api/scenarios'),
  golden: (scenario: string, artifact: string, offset = 0, limit = 40) =>
    req<GoldenPage>(`/api/golden?scenario=${encodeURIComponent(scenario)}&artifact=${encodeURIComponent(artifact)}&offset=${offset}&limit=${limit}`),
  java: (program: string) => req<SourceFile[]>(`/api/code/${program}/java`),
  cobol: (program: string) => req<CobolSource>(`/api/code/${program}/cobol`),

  // runs and jobs
  runs: (projectId?: string) => req<RunSummary[]>(`/api/runs${projectId ? `?project_id=${projectId}` : ''}`),
  run: (source: string, name: string) => req<RunDetail>(`/api/runs/${source}/${name}`),
  iteration: (source: string, name: string, n: number) => req<IterationDetail>(`/api/runs/${source}/${name}/iterations/${n}`),
  jobs: (projectId?: string) => req<Job[]>(`/api/jobs${projectId ? `?project_id=${projectId}` : ''}`),
  startMigrate: (p: MigrateRequest) => send<Job>('POST', '/api/jobs/migrate', p),
  startVerify: (projectId?: string, only = '') => send<Job>('POST', '/api/jobs/verify', { only, project_id: projectId ?? null }),
  startBuild: () => send<Job>('POST', '/api/jobs/build'),
  startMutation: () => send<Job>('POST', '/api/jobs/mutation'),
  cancel: (id: string) => send<Job>('POST', `/api/jobs/${id}/cancel`),
  answerGate: (id: string, gateId: string, action: 'approve' | 'stop', hint: string) =>
    send<{ ok: boolean }>('POST', `/api/jobs/${id}/gate`, { gate_id: gateId, action, hint }),
  eventsUrl: (id: string) => `${BASE}/api/jobs/${id}/events?token=${encodeURIComponent(tokenStore.get() ?? '')}`,

  // projects and the orchestration board
  budgets: (projectId: string) => req<Budgets>(`/api/projects/${projectId}/budgets`),
  board: (projectId: string) => req<{ graph: BoardGraph; compiled: Compiled; editable: boolean; updated: number | null }>(`/api/projects/${projectId}/board`),
  saveBoard: (projectId: string, g: BoardGraph) => send<{ compiled: Compiled }>('PUT', `/api/projects/${projectId}/board`, g),
  validateBoard: (projectId: string, g: BoardGraph) => send<Compiled>('POST', `/api/projects/${projectId}/board/validate`, g),
  runBoard: (projectId: string, g: BoardGraph) => send<Job>('POST', `/api/projects/${projectId}/board/run`, g),

  // admin
  adminUsers: () => req<AdminUser[]>('/api/admin/users'),
  createUser: (u: { email: string; name: string; role: string; password: string }) => send<{ id: string }>('POST', '/api/admin/users', u),
  patchUser: (id: string, p: Record<string, unknown>) => send<{ ok: boolean }>('PATCH', `/api/admin/users/${id}`, p),
  adminTeams: () => req<Team[]>('/api/admin/teams'),
  saveTeam: (id: string | null, t: Omit<Team, 'id'>) => (id ? send<{ ok: boolean }>('PUT', `/api/admin/teams/${id}`, t) : send<{ id: string }>('POST', '/api/admin/teams', t)),
  deleteTeam: (id: string) => send<{ ok: boolean }>('DELETE', `/api/admin/teams/${id}`),
  adminProjects: () => req<AdminProject[]>('/api/admin/projects'),
  saveProject: (id: string | null, p: Record<string, unknown>) => (id ? send<{ ok: boolean }>('PUT', `/api/admin/projects/${id}`, p) : send<{ id: string }>('POST', '/api/admin/projects', p)),
  policies: () => req<{ roles: string[]; policies: Record<string, Policy> }>('/api/admin/policies'),
  savePolicy: (role: string, p: Policy) => send<Policy>('PUT', `/api/admin/policies/${role}`, p),
  provider: () => req<ProviderCfg>('/api/admin/provider'),
  saveProvider: (p: Record<string, unknown>) => send<ProviderCfg>('PUT', '/api/admin/provider', p),
  removeKey: () => send<{ ok: boolean }>('DELETE', '/api/admin/provider/key'),
  testProvider: () => send<{ ok: boolean; message: string; missing?: string[] }>('POST', '/api/admin/provider/test'),
  usage: () => req<Usage>('/api/admin/usage'),
  audit: () => req<AuditRow[]>('/api/admin/audit'),
}
