import { Link, useNavigate } from 'react-router-dom'
import PipelineDiagram from '../components/PipelineDiagram'
import { Badge, Card, Empty, Spinner, Stat, statusTone } from '../components/ui'
import { api } from '../lib/api'
import { ago, num, pct } from '../lib/format'
import { useAuth } from '../lib/AuthContext'
import { useJob } from '../lib/JobContext'
import { useAsync } from '../lib/useAsync'

export default function Dashboard() {
  const env = useAsync(api.environment, [])
  const { project, can, profile } = useAuth()
  const runs = useAsync(() => api.runs(project?.id), [project?.id])
  const scen = useAsync(api.scenarios, [])
  const programs = useAsync(api.programs, [])
  const { start, busy, job } = useJob()
  const nav = useNavigate()

  const real = (runs.data ?? []).filter((r) => !r.is_mock)
  const passed = real.filter((r) => r.verdict === 'PASS').length
  const tokens = real.reduce((a, r) => a + r.prompt_tokens + r.output_tokens, 0)
  const cases = (scen.data ?? []).reduce((a, s) => a + s.case_count, 0)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-fg">{project ? project.name : 'Migration Studio'}</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-400">
          Signed in as {profile?.user.name} ({profile?.user.role_label}). Gemini ports CardDemo's COBOL batch programs to Java Spring Batch. Every claim is checked by diffing each output record against what the real COBOL produced.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Programs" value={programs.data?.length ?? '-'} hint="CBTRN02C, CBACT04C" tone="brand" />
        <Stat label="Oracle scenarios" value={scen.data?.length ?? '-'} hint={`${num(cases)} labelled edge cases`} />
        <Stat label="Gemini migrations passed" value={`${passed}/${real.length}`} hint="real model runs only" tone={passed === real.length && real.length ? 'ok' : 'warn'} />
        <Stat label="Tokens spent" value={num(tokens)} hint="prompt + output, all real runs" />
      </div>

      <Card title="How it works"><PipelineDiagram /></Card>

      <div className="grid gap-6 xl:grid-cols-3">
        <Card title="Latest migrations" className="xl:col-span-2" right={<Link to="/runs" className="text-xs text-brand-soft hover:underline">all runs</Link>}>
          {runs.loading ? <div className="p-6"><Spinner /></div> : !runs.data?.length ? <Empty>No runs yet. Open the Migration Studio and start one.</Empty> : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-[10px] uppercase tracking-wider text-slate-500">
                  <tr className="border-b border-ink-600/60">
                    {['Program', 'Model', 'Mode', 'Repairs', 'Records', 'Verdict', 'When'].map((h) => <th key={h} className="px-4 py-2 font-medium">{h}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {runs.data.slice(0, 7).map((r) => (
                    <tr key={r.id} className="cursor-pointer border-b border-ink-600/30 last:border-0 hover:bg-ink-800/60" onClick={() => nav(`/runs/${r.source}/${r.name}`)}>
                      <td className="px-4 py-2 font-mono text-xs text-fg">{r.program}</td>
                      <td className="px-4 py-2 text-slate-400">{r.is_mock ? <Badge tone="warn">mock</Badge> : r.model}</td>
                      <td className="px-4 py-2 text-slate-400">{r.mode}</td>
                      <td className="px-4 py-2 tabular-nums">{r.repairs}</td>
                      <td className="px-4 py-2 tabular-nums text-slate-400">{pct(r.final_records_matched ?? 0, r.records_total ?? 0)}</td>
                      <td className="px-4 py-2"><Badge tone={statusTone(r.verdict)}>{r.verdict}</Badge></td>
                      <td className="px-4 py-2 text-xs text-slate-500">{ago(r.created)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <div className="space-y-6">
          <Card title="Environment" right={<button className="text-xs text-brand-soft hover:underline" onClick={env.reload}>recheck</button>}>
            <ul className="divide-y divide-ink-600/30">
              {(env.data?.checks ?? []).map((c) => (
                <li key={c.id} className="flex items-start gap-3 px-4 py-2.5">
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${c.ok ? 'bg-ok' : 'bg-warn'}`} />
                  <div className="min-w-0">
                    <div className="text-sm text-slate-200">{c.label}</div>
                    <div className="truncate text-xs text-slate-500" title={c.detail}>{c.detail}</div>
                  </div>
                </li>
              ))}
              {env.loading && <li className="p-4"><Spinner /></li>}
            </ul>
          </Card>
          <Card title="Quick actions">
            <div className="grid gap-2 p-4">
              <button className="btn btn-primary" onClick={() => { void start(() => api.startVerify(project?.id)); nav('/verifier') }} disabled={busy || !can('can_run_verifier')}>Verify all 8 scenarios</button>
              <button className="btn" onClick={() => nav('/studio')}>Start a migration</button>
              <button className="btn" onClick={() => { void start(api.startBuild); }} disabled={busy || !can('can_run_build')}>Build Java project</button>
              {job && <p className="text-xs text-slate-500">Last job: {job.kind} ({job.status})</p>}
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
