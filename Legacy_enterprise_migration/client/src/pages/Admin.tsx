import { useEffect, useState, type ReactNode } from 'react'
import { RoleBadge } from '../components/Layout'
import { Badge, Card, Empty, ErrorNote, ProgressBar, Spinner, Tabs } from '../components/ui'
import { api } from '../lib/api'
import { num } from '../lib/format'
import { useAsync } from '../lib/useAsync'
import type { AdminProject, Policy, ProviderCfg, Role, Team } from '../lib/types'

const ROLES: { id: Role; label: string }[] = [
  { id: 'project_admin', label: 'Project Admin' }, { id: 'lead_architect', label: 'Lead Architect' }, { id: 'senior_dev', label: 'Senior Developer' },
  { id: 'junior_dev', label: 'Junior Developer' }, { id: 'intern', label: 'Intern' },
]
const AGENTS = [
  ['source', 'COBOL Source'], ['generator', 'Code Generator'], ['build', 'Build'], ['verify', 'Verifier'], ['repair', 'Repair Loop'], ['gate', 'Human Review Gate'], ['done', 'Result'],
]

function Notice({ ok, children }: { ok: boolean; children: ReactNode }) {
  return <div className={`rounded-lg border px-3 py-2 text-sm ${ok ? 'border-ok/30 bg-ok/10 text-ok' : 'border-bad/30 bg-bad/10 text-bad'}`}>{children}</div>
}

function useSaver() {
  const [state, setState] = useState<{ ok: boolean; msg: string } | null>(null)
  const run = async (fn: () => Promise<unknown>, okMsg: string) => {
    try { await fn(); setState({ ok: true, msg: okMsg }); return true } catch (e) { setState({ ok: false, msg: (e as Error).message }); return false }
  }
  return { state, run }
}

function Checks<T extends string>({ all, value, onChange }: { all: [T, string][]; value: T[]; onChange: (v: T[]) => void }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1">
      {all.map(([id, label]) => (
        <label key={id} className="flex items-center gap-1.5 text-sm text-slate-300">
          <input type="checkbox" checked={value.includes(id)} onChange={(e) => onChange(e.target.checked ? [...value, id] : value.filter((x) => x !== id))} /> {label}
        </label>
      ))}
    </div>
  )
}

// ------------------------------------------------------------------ users
function Users() {
  const users = useAsync(api.adminUsers, [])
  const { state, run } = useSaver()
  const [f, setF] = useState({ email: '', name: '', role: 'junior_dev', password: '' })
  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
      <Card title="Onboarded users">
        {users.loading ? <div className="p-6"><Spinner /></div> : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-[10px] uppercase tracking-wider text-slate-500"><tr className="border-b border-ink-600/60">{['User', 'Role', 'Teams', 'Projects', 'Active'].map((h) => <th key={h} className="px-4 py-2 font-medium">{h}</th>)}</tr></thead>
              <tbody>
                {(users.data ?? []).map((u) => (
                  <tr key={u.id} className="border-b border-ink-600/30">
                    <td className="px-4 py-2"><div className="font-medium text-fg">{u.name}</div><div className="text-xs text-slate-500">{u.email}</div></td>
                    <td className="px-4 py-2">
                      <select className="input w-auto py-1" value={u.role} aria-label={`role for ${u.name}`}
                        onChange={(e) => void run(() => api.patchUser(u.id, { role: e.target.value }), `${u.name} is now ${e.target.value}`).then(users.reload)}>
                        {ROLES.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
                      </select>
                    </td>
                    <td className="px-4 py-2 text-xs text-slate-400">{u.teams.join(', ') || '-'}</td>
                    <td className="px-4 py-2 text-xs text-slate-400">{u.projects.join(', ') || '-'}</td>
                    <td className="px-4 py-2">
                      <input type="checkbox" checked={!!u.active} aria-label={`active ${u.name}`} onChange={(e) => void run(() => api.patchUser(u.id, { active: e.target.checked }), 'Saved').then(users.reload)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <Card title="Onboard a user">
        <form className="space-y-3 p-4" onSubmit={(e) => { e.preventDefault(); void run(() => api.createUser(f), `${f.name} onboarded`).then((ok) => { if (ok) { setF({ email: '', name: '', role: 'junior_dev', password: '' }); users.reload() } }) }}>
          <div><label className="label" htmlFor="un">Name</label><input id="un" className="input" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
          <div><label className="label" htmlFor="ue">Email</label><input id="ue" className="input" type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></div>
          <div><label className="label" htmlFor="ur">Role</label>
            <select id="ur" className="input" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{ROLES.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}</select></div>
          <div><label className="label" htmlFor="up">Initial password (8+ chars)</label><input id="up" className="input" type="password" minLength={8} required value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></div>
          <button className="btn btn-primary w-full">Onboard</button>
          {state && <Notice ok={state.ok}>{state.msg}</Notice>}
        </form>
      </Card>
    </div>
  )
}

// ------------------------------------------------------------------ teams and projects
function Teams() {
  const teams = useAsync(api.adminTeams, [])
  const users = useAsync(api.adminUsers, [])
  const { state, run } = useSaver()
  const blank: Omit<Team, 'id'> = { name: '', daily_token_budget: 200000, members: [] }
  const [edit, setEdit] = useState<{ id: string | null; t: Omit<Team, 'id'> }>({ id: null, t: blank })
  const save = () => void run(() => api.saveTeam(edit.id, edit.t), 'Team saved').then((ok) => { if (ok) { setEdit({ id: null, t: blank }); teams.reload() } })
  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
      <Card title="Teams">
        {!teams.data?.length ? <Empty>No teams yet.</Empty> : (
          <ul className="divide-y divide-ink-600/30">
            {teams.data.map((t) => (
              <li key={t.id} className="flex items-start justify-between gap-3 px-4 py-3">
                <div>
                  <div className="font-medium text-fg">{t.name}</div>
                  <div className="text-xs text-slate-500">{t.members.length} members - daily budget {t.daily_token_budget == null ? 'unlimited' : num(t.daily_token_budget) + ' tokens'}</div>
                  <div className="mt-1 text-xs text-slate-400">{t.members.map((m) => users.data?.find((u) => u.id === m)?.name).filter(Boolean).join(', ')}</div>
                </div>
                <div className="flex gap-2">
                  <button className="btn px-2.5 py-1 text-xs" onClick={() => setEdit({ id: t.id, t: { name: t.name, daily_token_budget: t.daily_token_budget, members: t.members } })}>Edit</button>
                  <button className="btn btn-danger px-2.5 py-1 text-xs" onClick={() => void run(() => api.deleteTeam(t.id), 'Team deleted').then(teams.reload)}>Delete</button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title={edit.id ? 'Edit team' : 'New team'}>
        <div className="space-y-3 p-4">
          <div><label className="label" htmlFor="tn">Name</label><input id="tn" className="input" value={edit.t.name} onChange={(e) => setEdit({ ...edit, t: { ...edit.t, name: e.target.value } })} /></div>
          <div><label className="label" htmlFor="tb">Daily Gemini token limit for the whole team (blank = unlimited)</label>
            <input id="tb" className="input" type="number" min={0} value={edit.t.daily_token_budget ?? ''} onChange={(e) => setEdit({ ...edit, t: { ...edit.t, daily_token_budget: e.target.value === '' ? null : Number(e.target.value) } })} /></div>
          <div><span className="label">Members</span>
            <Checks all={(users.data ?? []).map((u) => [u.id, u.name] as [string, string])} value={edit.t.members} onChange={(m) => setEdit({ ...edit, t: { ...edit.t, members: m } })} /></div>
          <div className="flex gap-2"><button className="btn btn-primary" disabled={!edit.t.name.trim()} onClick={save}>{edit.id ? 'Save team' : 'Create team'}</button>
            {edit.id && <button className="btn" onClick={() => setEdit({ id: null, t: blank })}>Cancel</button>}</div>
          {state && <Notice ok={state.ok}>{state.msg}</Notice>}
        </div>
      </Card>
    </div>
  )
}

function Projects() {
  const projects = useAsync(api.adminProjects, [])
  const users = useAsync(api.adminUsers, [])
  const teams = useAsync(api.adminTeams, [])
  const { state, run } = useSaver()
  const blank = { name: '', description: '', token_budget: 1000000 as number | null, users: [] as string[], teams: [] as string[], archived: false }
  const [edit, setEdit] = useState<{ id: string | null; p: typeof blank }>({ id: null, p: blank })
  const save = () => void run(() => api.saveProject(edit.id, edit.p), 'Project saved').then((ok) => { if (ok) { setEdit({ id: null, p: blank }); projects.reload() } })
  const open = (p: AdminProject) => setEdit({ id: p.id, p: { name: p.name, description: p.description, token_budget: p.token_budget, users: p.users, teams: p.teams, archived: !!p.archived } })
  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_400px]">
      <Card title="Projects">
        {!projects.data?.length ? <Empty>No projects yet.</Empty> : (
          <ul className="divide-y divide-ink-600/30">
            {projects.data.map((p) => (
              <li key={p.id} className="space-y-1.5 px-4 py-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-medium text-fg">{p.name} {p.archived ? <Badge>archived</Badge> : null}</div>
                  <button className="btn px-2.5 py-1 text-xs" onClick={() => open(p)}>Edit / assign</button>
                </div>
                <div className="text-xs text-slate-500">{p.description}</div>
                <div className="text-xs text-slate-400">
                  Teams: {p.teams.map((t) => teams.data?.find((x) => x.id === t)?.name).filter(Boolean).join(', ') || '-'} - Direct users: {p.users.map((u) => users.data?.find((x) => x.id === u)?.name).filter(Boolean).join(', ') || '-'}
                </div>
                {p.token_budget != null && <div><div className="flex justify-between text-[11px] text-slate-500"><span>token budget</span><span className="tabular-nums">{num(p.tokens_used)} / {num(p.token_budget)}</span></div>
                  <ProgressBar value={p.tokens_used} total={p.token_budget || 1} tone={p.tokens_used >= p.token_budget ? 'bad' : 'brand'} /></div>}
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title={edit.id ? 'Edit project' : 'New project'}>
        <div className="space-y-3 p-4">
          <div><label className="label" htmlFor="pn">Name</label><input id="pn" className="input" value={edit.p.name} onChange={(e) => setEdit({ ...edit, p: { ...edit.p, name: e.target.value } })} /></div>
          <div><label className="label" htmlFor="pd">Description</label><input id="pd" className="input" value={edit.p.description} onChange={(e) => setEdit({ ...edit, p: { ...edit.p, description: e.target.value } })} /></div>
          <div><label className="label" htmlFor="pb">Total Gemini token budget (blank = unlimited)</label>
            <input id="pb" className="input" type="number" min={0} value={edit.p.token_budget ?? ''} onChange={(e) => setEdit({ ...edit, p: { ...edit.p, token_budget: e.target.value === '' ? null : Number(e.target.value) } })} /></div>
          <div><span className="label">Assign teams</span><Checks all={(teams.data ?? []).map((t) => [t.id, t.name] as [string, string])} value={edit.p.teams} onChange={(v) => setEdit({ ...edit, p: { ...edit.p, teams: v } })} /></div>
          <div><span className="label">Assign individual users</span><Checks all={(users.data ?? []).map((u) => [u.id, u.name] as [string, string])} value={edit.p.users} onChange={(v) => setEdit({ ...edit, p: { ...edit.p, users: v } })} /></div>
          {edit.id && <label className="flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" checked={edit.p.archived} onChange={(e) => setEdit({ ...edit, p: { ...edit.p, archived: e.target.checked } })} /> archived (hidden from members)</label>}
          <div className="flex gap-2"><button className="btn btn-primary" disabled={!edit.p.name.trim()} onClick={save}>{edit.id ? 'Save project' : 'Create project'}</button>
            {edit.id && <button className="btn" onClick={() => setEdit({ id: null, p: blank })}>Cancel</button>}</div>
          {state && <Notice ok={state.ok}>{state.msg}</Notice>}
        </div>
      </Card>
    </div>
  )
}

// ------------------------------------------------------------------ role policies
function Policies() {
  const data = useAsync(api.policies, [])
  const [role, setRole] = useState<Role>('junior_dev')
  const [pol, setPol] = useState<Policy | null>(null)
  const { state, run } = useSaver()
  useEffect(() => { if (data.data) setPol(data.data.policies[role]) }, [data.data, role])
  if (!pol) return <Spinner />
  const num_ = (k: 'max_repairs' | 'runs_per_day' | 'daily_token_budget', label: string, max?: number) => (
    <div><label className="label" htmlFor={k}>{label}</label>
      <input id={k} className="input" type="number" min={0} max={max} value={pol[k]} onChange={(e) => setPol({ ...pol, [k]: Number(e.target.value) })} /></div>
  )
  const flags: [keyof Policy, string][] = [['can_approve_gates', 'Approve human review gates'], ['can_edit_board', 'Edit the orchestration board'], ['can_run_verifier', 'Run the verifier'], ['can_run_build', 'Rebuild the Java project'], ['can_run_mutation', 'Run the mutation check']]
  return (
    <Card title="What each role can do with the AI agents" right={<Tabs tabs={ROLES.map((r) => ({ id: r.id, label: r.label }))} value={role} onChange={setRole} />}>
      <div className="grid gap-5 p-4 lg:grid-cols-2">
        <div className="space-y-4">
          <div><span className="label">AI providers</span><Checks all={[['mock', 'Mock (offline)'], ['gemini', 'Gemini']]} value={pol.providers} onChange={(v) => setPol({ ...pol, providers: v })} /></div>
          <div><label className="label" htmlFor="tier">Gemini model tier (strength)</label>
            <select id="tier" className="input" value={pol.model_tier} onChange={(e) => setPol({ ...pol, model_tier: e.target.value as Policy['model_tier'] })}>
              <option value="none">none (no Gemini)</option><option value="basic">basic (flash-class)</option><option value="advanced">advanced (pro-class)</option></select></div>
          <div><span className="label">Prompt modes</span><Checks all={[['guided', 'guided'], ['naive', 'naive']]} value={pol.modes} onChange={(v) => setPol({ ...pol, modes: v })} /></div>
          <div><span className="label">AI agents this role may use on the board and in runs</span>
            <Checks all={AGENTS as [string, string][]} value={pol.agents} onChange={(v) => setPol({ ...pol, agents: v })} /></div>
        </div>
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-3">{num_('max_repairs', 'Max repairs', 8)}{num_('runs_per_day', 'Runs / day')}{num_('daily_token_budget', 'Tokens / day')}</div>
          <div className="space-y-1.5"><span className="label">Permissions</span>
            {flags.map(([k, label]) => (
              <label key={k} className="flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" checked={!!pol[k]} onChange={(e) => setPol({ ...pol, [k]: e.target.checked })} /> {label}</label>
            ))}
          </div>
          <button className="btn btn-primary" onClick={() => void run(() => api.savePolicy(role, pol), `${role} policy saved`).then(data.reload)}>Save policy for {ROLES.find((r) => r.id === role)?.label}</button>
          {role === 'project_admin' && <p className="text-xs text-slate-500">The admin role always keeps every agent and the approval rights, so it cannot lock itself out.</p>}
          {state && <Notice ok={state.ok}>{state.msg}</Notice>}
        </div>
      </div>
    </Card>
  )
}

// ------------------------------------------------------------------ Gemini provider
function Provider() {
  const prov = useAsync(api.provider, [])
  const { state, run } = useSaver()
  const [cfg, setCfg] = useState<ProviderCfg | null>(null)
  const [key, setKey] = useState('')
  const [test, setTest] = useState<{ ok: boolean; message: string; missing?: string[] } | null>(null)
  const [testing, setTesting] = useState(false)
  useEffect(() => { if (prov.data) setCfg(prov.data) }, [prov.data])
  if (!cfg) return <Spinner />
  const save = () => void run(() => api.saveProvider({ enabled: cfg.enabled, models: cfg.models, default_model: cfg.default_model, ...(key.trim() ? { api_key: key.trim() } : {}) }), key.trim() ? 'Provider and key saved (key stored encrypted)' : 'Provider saved').then((ok) => { if (ok) { setKey(''); prov.reload() } })
  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <Card title="Gemini API provider" right={<Badge tone={cfg.has_key ? 'ok' : 'warn'}>{cfg.has_key ? 'key configured' : 'no key'}</Badge>}>
        <div className="space-y-4 p-4">
          <label className="flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" checked={cfg.enabled} onChange={(e) => setCfg({ ...cfg, enabled: e.target.checked })} /> Provider enabled (when off, nobody can start Gemini runs)</label>
          <div>
            <label className="label" htmlFor="gk">API key {cfg.key_hint && <span className="normal-case text-slate-500">current: {cfg.key_hint}</span>}</label>
            <input id="gk" className="input font-mono" type="password" autoComplete="off" placeholder={cfg.has_key ? 'leave blank to keep the stored key' : 'paste a Google AI Studio key'} value={key} onChange={(e) => setKey(e.target.value)} />
            <p className="mt-1 text-xs text-slate-500">Stored encrypted on the server, injected only into the migration process, never sent back to the browser.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="btn btn-primary" onClick={save}>Save</button>
            <button className="btn" disabled={!cfg.has_key || testing} onClick={() => { setTesting(true); void api.testProvider().then(setTest).catch((e: Error) => setTest({ ok: false, message: e.message })).finally(() => setTesting(false)) }}>{testing ? <Spinner /> : 'Test connection'}</button>
            <button className="btn btn-danger" disabled={!cfg.has_key} onClick={() => void run(() => api.removeKey(), 'Key removed').then(prov.reload)}>Remove key</button>
          </div>
          {test && <Notice ok={test.ok}>{test.message}{test.missing?.length ? ` Not found at Google: ${test.missing.join(', ')}` : ''}</Notice>}
          {state && <Notice ok={state.ok}>{state.msg}</Notice>}
          <p className="text-xs text-slate-500">Test connection asks Google's Models API for the model list with this key; the key only goes to Google.</p>
        </div>
      </Card>
      <Card title="Models and tiers">
        <div className="space-y-3 p-4">
          <p className="text-xs text-slate-500">Roles are allowed models up to their tier: basic roles get basic models, advanced roles get both. Add the model ids your key can use.</p>
          {cfg.models.map((m, i) => (
            <div key={i} className="flex items-center gap-2">
              <input className="input font-mono" aria-label="model id" value={m.id} onChange={(e) => setCfg({ ...cfg, models: cfg.models.map((x, j) => (j === i ? { ...x, id: e.target.value } : x)) })} />
              <select className="input w-32" aria-label="tier" value={m.tier} onChange={(e) => setCfg({ ...cfg, models: cfg.models.map((x, j) => (j === i ? { ...x, tier: e.target.value as 'basic' | 'advanced' } : x)) })}>
                <option value="basic">basic</option><option value="advanced">advanced</option></select>
              <label className="flex items-center gap-1 text-xs text-slate-400"><input type="radio" name="dm" checked={cfg.default_model === m.id} onChange={() => setCfg({ ...cfg, default_model: m.id })} /> default</label>
              <button className="btn btn-danger px-2 py-1 text-xs" disabled={cfg.models.length < 2} onClick={() => setCfg({ ...cfg, models: cfg.models.filter((_, j) => j !== i), default_model: cfg.default_model === m.id ? cfg.models.find((_, j) => j !== i)!.id : cfg.default_model })}>x</button>
            </div>
          ))}
          <button className="btn" onClick={() => setCfg({ ...cfg, models: [...cfg.models, { id: 'gemini-', tier: 'advanced' }] })}>+ Add model</button>
        </div>
      </Card>
    </div>
  )
}

// ------------------------------------------------------------------ usage and audit
function UsageAudit() {
  const usage = useAsync(api.usage, [])
  const audit = useAsync(api.audit, [])
  const when = (ts: number) => new Date(ts * 1000).toLocaleString()
  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <Card title="Gemini usage by user">
        {!usage.data ? <Spinner /> : (
          <table className="w-full text-left text-sm"><thead className="text-[10px] uppercase tracking-wider text-slate-500"><tr className="border-b border-ink-600/60"><th className="px-4 py-2">User</th><th>Role</th><th>Runs</th><th>Tokens</th></tr></thead>
            <tbody>{usage.data.by_user.map((u) => <tr key={u.name} className="border-b border-ink-600/30"><td className="px-4 py-2 text-fg">{u.name}</td><td><RoleBadge role={u.role} /></td><td className="tabular-nums">{u.runs}</td><td className="tabular-nums">{num(u.tokens)}</td></tr>)}</tbody></table>
        )}
      </Card>
      <Card title="Usage by project">
        {!usage.data ? <Spinner /> : (
          <table className="w-full text-left text-sm"><thead className="text-[10px] uppercase tracking-wider text-slate-500"><tr className="border-b border-ink-600/60"><th className="px-4 py-2">Project</th><th>Runs</th><th>Tokens</th><th>Budget</th></tr></thead>
            <tbody>{usage.data.by_project.map((p) => <tr key={p.name} className="border-b border-ink-600/30"><td className="px-4 py-2 text-fg">{p.name}</td><td className="tabular-nums">{p.runs}</td><td className="tabular-nums">{num(p.tokens)}</td><td className="tabular-nums">{p.token_budget == null ? 'unlimited' : num(p.token_budget)}</td></tr>)}</tbody></table>
        )}
      </Card>
      <Card title="Audit log" className="xl:col-span-2">
        {!audit.data?.length ? <Empty>Nothing logged yet.</Empty> : (
          <div className="max-h-[360px] overflow-auto"><table className="w-full text-left text-xs"><thead className="sticky top-0 bg-ink-900 text-[10px] uppercase tracking-wider text-slate-500"><tr><th className="px-4 py-2">When</th><th>Who</th><th>Action</th><th>Detail</th></tr></thead>
            <tbody>{audit.data.map((a, i) => <tr key={i} className="border-t border-ink-600/30"><td className="whitespace-nowrap px-4 py-1.5 text-slate-500">{when(a.ts)}</td><td className="text-slate-300">{a.user ?? '-'}</td><td className="font-mono text-brand-soft">{a.action}</td><td className="text-slate-400">{a.detail}</td></tr>)}</tbody></table></div>
        )}
      </Card>
    </div>
  )
}

export default function Admin() {
  const [tab, setTab] = useState<'users' | 'teams' | 'projects' | 'policies' | 'provider' | 'usage'>('provider')
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold text-fg">Admin and IAM</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-400">Onboard people, group them into teams, assign teams to projects, decide what each role may do with the AI agents, and connect the Gemini provider with its budgets.</p>
      </div>
      <Tabs tabs={[{ id: 'provider', label: 'AI Providers' }, { id: 'policies', label: 'Role policies' }, { id: 'users', label: 'Users' }, { id: 'teams', label: 'Teams' }, { id: 'projects', label: 'Projects' }, { id: 'usage', label: 'Usage and audit' }]} value={tab} onChange={setTab} />
      <ErrorNote message={null} />
      {tab === 'users' && <Users />}
      {tab === 'teams' && <Teams />}
      {tab === 'projects' && <Projects />}
      {tab === 'policies' && <Policies />}
      {tab === 'provider' && <Provider />}
      {tab === 'usage' && <UsageAudit />}
    </div>
  )
}
