import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Convergence from '../components/Convergence'
import HumanGate from '../components/HumanGate'
import MigrationTree from '../components/MigrationTree'
import { Badge, Card, ErrorNote, LogView, ProgressBar, Spinner, Tabs, statusTone } from '../components/ui'
import { api } from '../lib/api'
import { useAuth } from '../lib/AuthContext'
import { num, splitRunId } from '../lib/format'
import { useJob } from '../lib/JobContext'
import { useAsync } from '../lib/useAsync'

const TIER_RANK = { none: 0, basic: 1, advanced: 2 }

function Budget({ label, used, limit }: { label: string; used: number; limit: number }) {
  return (
    <div>
      <div className="flex justify-between text-[11px] text-slate-500"><span>{label}</span><span className="tabular-nums">{num(used)} / {num(limit)}</span></div>
      <ProgressBar value={used} total={limit || 1} tone={limit && used >= limit ? 'bad' : 'brand'} />
    </div>
  )
}

export default function Studio() {
  const { profile, project, hasAgent, refresh } = useAuth()
  const programs = useAsync(api.programs, [])
  const env = useAsync(api.environment, [])
  const { start, busy, job, attempts, logs, events, error } = useJob()
  const pol = profile!.policy
  const models = profile!.provider.models.filter((m) => TIER_RANK[m.tier] <= TIER_RANK[pol.model_tier])
  const canGemini = pol.providers.includes('gemini') && profile!.provider.enabled && profile!.provider.has_key && models.length > 0
  const maxRepairs = hasAgent('repair') ? pol.max_repairs : 0

  const [program, setProgram] = useState('posttran')
  const [provider, setProvider] = useState<'mock' | 'gemini'>('mock')
  const [mode, setMode] = useState(pol.modes[0] ?? 'guided')
  const [repairs, setRepairs] = useState(Math.min(4, maxRepairs))
  const [model, setModel] = useState(profile!.provider.default_model)
  const [gateGen, setGateGen] = useState(false)
  const [gateRep, setGateRep] = useState(false)
  const [view, setView] = useState<'tree' | 'chart'>('tree')

  useEffect(() => { if (models.length && !models.some((m) => m.id === model)) setModel(models[0].id) }, [models, model])
  useEffect(() => { void refresh() }, [job?.status === 'passed' || job?.status === 'failed']) // eslint-disable-line react-hooks/exhaustive-deps

  const needsSrc = env.data?.checks.find((c) => c.id === 'carddemo')?.ok === false
  const gates = [gateGen && 'generate', gateRep && 'repair'].filter(Boolean) as string[]
  const isMigration = job?.kind === 'migrate'
  const runId = isMigration && typeof job.result.run === 'string' ? splitRunId(job.result.run) : null
  const mine = isMigration && job?.owner.user_id === profile!.user.id
  const b = profile!.budgets

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-fg">Migration Studio</h1>
          <p className="mt-1 text-sm text-slate-400">Port a COBOL program, watch the decision tree grow, and step in when the run asks for a human.</p>
        </div>
        {project && <Badge tone="brand">project: {project.name}</Badge>}
      </div>

      <HumanGate />

      <div className="grid gap-6 xl:grid-cols-[320px_1fr]">
        <Card title="Configure">
          <div className="space-y-4 p-4">
            <div>
              <span className="label">COBOL program</span>
              <div className="grid gap-2">
                {(programs.data ?? []).map((p) => (
                  <button key={p.id} onClick={() => setProgram(p.id)}
                    className={`rounded-lg border px-3 py-2 text-left transition ${program === p.id ? 'border-brand bg-brand/10' : 'border-ink-600 bg-ink-800 hover:border-slate-500'}`}>
                    <div className="flex items-center justify-between"><span className="font-mono text-sm text-fg">{p.cobol}</span><span className="text-xs text-slate-500">{p.id}</span></div>
                    <div className="text-xs text-slate-400">{p.title}</div>
                  </button>
                ))}
              </div>
            </div>

            <div>
              <span className="label">AI provider</span>
              <div className="grid grid-cols-2 gap-2">
                <button className={`btn ${provider === 'mock' ? 'border-brand text-brand-soft' : ''}`} onClick={() => setProvider('mock')}>Mock (offline)</button>
                <button className={`btn ${provider === 'gemini' ? 'border-brand text-brand-soft' : ''}`} disabled={!canGemini} onClick={() => setProvider('gemini')}
                  title={canGemini ? '' : !pol.providers.includes('gemini') ? 'Your role cannot use Gemini' : 'An admin must configure the Gemini key and models'}>Gemini</button>
              </div>
              {!canGemini && (
                <p className="mt-1.5 text-xs text-slate-500">
                  {!pol.providers.includes('gemini') ? `Gemini is not available to your role (${profile!.user.role_label}).` : 'Gemini is not configured yet; an admin can add the key under Admin and IAM.'}
                </p>
              )}
              {provider === 'mock' && <p className="mt-1.5 text-xs text-slate-500">Scripted replay, not a model. It demonstrates the loop.</p>}
            </div>

            {provider === 'gemini' && (
              <div>
                <label className="label" htmlFor="model">Model</label>
                <select id="model" className="input font-mono" value={model} onChange={(e) => setModel(e.target.value)}>
                  {models.map((m) => <option key={m.id} value={m.id}>{m.id} ({m.tier})</option>)}
                </select>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label" htmlFor="mode">Prompt mode</label>
                <select id="mode" className="input" value={mode} onChange={(e) => setMode(e.target.value)}>
                  {pol.modes.map((m) => <option key={m} value={m}>{m === 'guided' ? 'guided (COBOL primer)' : 'naive (source only)'}</option>)}
                </select>
              </div>
              <div>
                <label className="label" htmlFor="rep">Max repairs (cap {maxRepairs})</label>
                <input id="rep" type="number" min={0} max={maxRepairs} disabled={maxRepairs === 0} className="input" value={repairs}
                  onChange={(e) => setRepairs(Math.max(0, Math.min(maxRepairs, Number(e.target.value) || 0)))} />
              </div>
            </div>

            <div>
              <span className="label">Human review gates</span>
              <label className={`flex items-center gap-2 text-sm ${hasAgent('gate') ? 'text-slate-300' : 'text-slate-600'}`}>
                <input type="checkbox" disabled={!hasAgent('gate')} checked={gateGen} onChange={(e) => setGateGen(e.target.checked)} /> before the first generation
              </label>
              <label className={`mt-1 flex items-center gap-2 text-sm ${hasAgent('gate') ? 'text-slate-300' : 'text-slate-600'}`}>
                <input type="checkbox" disabled={!hasAgent('gate')} checked={gateRep} onChange={(e) => setGateRep(e.target.checked)} /> before each repair
              </label>
              {!hasAgent('gate') && <p className="mt-1 text-xs text-slate-500">Placing review gates needs a senior role or above.</p>}
            </div>

            <div className="space-y-2 rounded-lg border border-ink-600/60 bg-ink-800/50 p-3">
              <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">Your budgets today ({profile!.user.role_label})</div>
              <Budget label="runs" used={b.runs.used} limit={b.runs.limit} />
              {pol.providers.includes('gemini') && <Budget label="Gemini tokens" used={b.user.used} limit={b.user.limit} />}
              {b.teams.map((t) => <Budget key={t.id} label={`team ${t.name}`} used={t.used} limit={t.limit} />)}
            </div>

            {needsSrc && <ErrorNote message="CardDemo COBOL source is missing on the server (set SRC)." />}
            <ErrorNote message={error} />
            <button className="btn btn-primary w-full" disabled={busy || !project || needsSrc}
              onClick={() => project && void start(() => api.startMigrate({ project_id: project.id, program, provider, mode, max_repairs: repairs, model: provider === 'gemini' ? model : undefined, gates }))}>
              {busy ? <><Spinner /> Running...</> : 'Start migration'}
            </button>
          </div>
        </Card>

        <div className="min-w-0 space-y-6">
          <Card title="Migration tree" right={
            <div className="flex items-center gap-3">
              {job && isMigration && <Badge tone={statusTone(job.status)}>{job.status}</Badge>}
              <Tabs tabs={[{ id: 'tree', label: 'Decision tree' }, { id: 'chart', label: 'Convergence' }]} value={view} onChange={setView} />
            </div>}>
            {busy && isMigration && <div className="px-4 pt-3"><ProgressBar value={0} total={1} indeterminate /></div>}
            {view === 'tree'
              ? <MigrationTree events={isMigration ? events : []} busy={busy && isMigration} maxRepairs={Number(job?.params.max_repairs ?? repairs)} gatePoints={isMigration ? ((job?.params.gates as string[]) ?? []) : gates} />
              : <Convergence points={(isMigration ? attempts : []).map((a) => ({ label: a.label, matched: a.records_matched, total: a.records_total, built: a.build }))} />}
            {isMigration && job && !mine && <p className="border-t border-ink-600/60 px-4 py-2 text-xs text-slate-500">Started by {job.owner.user_name ?? 'a teammate'}. You are watching live.</p>}
            {attempts.length > 0 && isMigration && (
              <div className="grid grid-cols-2 gap-px border-t border-ink-600/60 bg-ink-600/40 sm:grid-cols-4">
                {[
                  ['Attempts', attempts.length],
                  ['Scenarios passing', `${attempts[attempts.length - 1].scenarios_passed}/${attempts[attempts.length - 1].scenarios_total}`],
                  ['Tokens in', num(attempts.reduce((a, s) => a + s.prompt_tokens, 0))],
                  ['Tokens out', num(attempts.reduce((a, s) => a + s.output_tokens, 0))],
                ].map(([k, v]) => (
                  <div key={k as string} className="bg-ink-900 px-4 py-2.5"><div className="text-[10px] uppercase tracking-wider text-slate-500">{k}</div><div className="font-semibold tabular-nums text-fg">{v}</div></div>
                ))}
              </div>
            )}
          </Card>

          <Card title="Live output" right={runId ? <Link className="btn px-2.5 py-1 text-xs" to={`/runs/${runId[0]}/${runId[1]}`}>Open run report</Link> : undefined}>
            <LogView lines={isMigration ? logs : []} live={busy} />
          </Card>
        </div>
      </div>
    </div>
  )
}
