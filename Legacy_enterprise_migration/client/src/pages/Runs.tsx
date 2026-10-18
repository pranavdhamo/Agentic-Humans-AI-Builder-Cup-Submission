import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import Convergence from '../components/Convergence'
import { Badge, Card, Code, Empty, Spinner, Stat, Tabs, statusTone } from '../components/ui'
import { api } from '../lib/api'
import { ago, duration, num, pct } from '../lib/format'
import { useAuth } from '../lib/AuthContext'
import { useAsync } from '../lib/useAsync'

function Iterations({ source, name, available }: { source: string; name: string; available: number[] }) {
  const [n, setN] = useState(available[0] ?? 0)
  const [tab, setTab] = useState<'feedback' | 'code' | 'prompt' | 'notes'>('feedback')
  const [file, setFile] = useState(0)
  const it = useAsync(() => api.iteration(source, name, n), [source, name, n])
  const files = Object.entries(it.data?.files ?? {})

  return (
    <Card title="Attempt inspector" right={
      <div className="flex gap-1">{available.map((i) => (
        <button key={i} onClick={() => { setN(i); setFile(0) }} className={`rounded px-2 py-0.5 text-xs ${n === i ? 'bg-brand/15 text-brand-soft' : 'text-slate-500 hover:text-slate-200'}`}>{i === 0 ? 'generate' : `repair ${i}`}</button>
      ))}</div>}>
      <div className="flex items-center justify-between border-b border-ink-600/40 px-4 py-2">
        <Tabs tabs={[{ id: 'feedback', label: 'Verifier feedback' }, { id: 'code', label: `Generated Java (${files.length})` }, { id: 'prompt', label: 'Prompt' }, { id: 'notes', label: 'Model notes' }]} value={tab} onChange={setTab} />
        {it.loading && <Spinner />}
      </div>
      {tab === 'feedback' && <Code text={it.data?.feedback ?? ''} empty="No feedback stored." />}
      {tab === 'prompt' && <Code text={it.data?.prompt ?? ''} empty="No prompt stored." />}
      {tab === 'notes' && <Code text={it.data?.notes ?? ''} empty="The model left no notes." />}
      {tab === 'code' && (
        <div>
          <div className="flex flex-wrap gap-1 border-b border-ink-600/40 px-4 py-2">
            {files.map(([p], i) => (
              <button key={p} onClick={() => setFile(i)} className={`rounded px-2 py-0.5 font-mono text-[11px] ${file === i ? 'bg-ink-700 text-fg' : 'text-slate-500 hover:text-slate-200'}`}>{p.split('/').pop()}</button>
            ))}
          </div>
          <Code text={files[file]?.[1] ?? ''} empty="No files in this attempt." />
        </div>
      )}
    </Card>
  )
}

function Detail({ source, name }: { source: string; name: string }) {
  const d = useAsync(() => api.run(source, name), [source, name])
  if (d.loading) return <div className="p-8"><Spinner /></div>
  if (!d.data) return <Empty>{d.error ?? 'Run not found.'}</Empty>
  const s = d.data.summary
  const its = d.data.report.iterations
  const rules = Array.isArray(d.data.rules) ? d.data.rules : []

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-mono text-lg text-fg">{s.program}</h2>
        <Badge tone={statusTone(s.verdict)}>{s.verdict}</Badge>
        {s.is_mock ? <Badge tone="warn">mock provider (scripted)</Badge> : <Badge tone="brand">{s.model}</Badge>}
        <Badge>{s.mode}</Badge>
        <span className="text-xs text-slate-500">{s.name}</span>
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="First attempt" value={pct(s.first_records_matched ?? 0, s.records_total ?? 0)} hint="records identical to COBOL" />
        <Stat label="Final" value={pct(s.final_records_matched ?? 0, s.records_total ?? 0)} tone={s.verdict === 'PASS' ? 'ok' : 'bad'} hint={`${s.repairs} repair(s)`} />
        <Stat label="Tokens" value={num(s.prompt_tokens + s.output_tokens)} hint={`${num(s.prompt_tokens)} in / ${num(s.output_tokens)} out`} />
        <Stat label="Model time" value={duration(s.llm_seconds)} />
      </div>
      <Card title="Convergence">
        <Convergence points={its.map((i) => ({ label: i.iteration === 0 ? 'generate' : `repair ${i.iteration}`, matched: i.records_matched ?? 0, total: i.records_total ?? s.records_total ?? 0, built: i.build }))} />
      </Card>
      {d.data.iterations_available.length > 0 ? (
        <Iterations source={source} name={name} available={d.data.iterations_available} />
      ) : (
        <Card><Empty>Prompts and generated code are only stored for fresh runs. This curated result keeps the report and extracted rules.</Empty></Card>
      )}
      {rules.length > 0 && (
        <Card title={`Business rules the model extracted (${rules.length})`}>
          <ul className="divide-y divide-ink-600/30 text-sm">
            {rules.slice(0, 40).map((r: unknown, i: number) => (
              <li key={i} className="px-4 py-2 text-slate-300">{typeof r === 'string' ? r : JSON.stringify(r)}</li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}

export default function Runs() {
  const { source, name } = useParams()
  const { project } = useAuth()
  const runs = useAsync(() => api.runs(project?.id), [project?.id])
  const nav = useNavigate()
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-fg">Run History</h1>
        <p className="mt-1 text-sm text-slate-400">Curated Gemini results and every run started from this studio.</p>
      </div>
      <div className="grid gap-6 xl:grid-cols-[360px_1fr]">
        <Card title="Runs">
          {runs.loading ? <div className="p-6"><Spinner /></div> : !runs.data?.length ? <Empty>No runs yet.</Empty> : (
            <ul className="max-h-[70vh] divide-y divide-ink-600/30 overflow-y-auto">
              {runs.data.map((r) => {
                const on = r.source === source && r.name === name
                return (
                  <li key={r.id}>
                    <Link to={`/runs/${r.source}/${r.name}`} className={`block px-4 py-3 transition hover:bg-ink-800/70 ${on ? 'bg-brand/10' : ''}`}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono text-sm text-fg">{r.program}</span>
                        <Badge tone={statusTone(r.verdict)}>{r.verdict}</Badge>
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-slate-500">
                        <span>{r.is_mock ? 'mock' : r.model}</span><span>{r.mode}</span><span>{r.repairs} repair(s)</span><span>{ago(r.created)}</span>{r.started_by && <span>by {r.started_by}</span>}
                      </div>
                    </Link>
                  </li>
                )
              })}
            </ul>
          )}
        </Card>
        <div>
          {source && name ? <Detail source={source} name={name} /> : (
            <Card><Empty>Select a run{runs.data?.length ? '' : ', or start one in the Migration Studio'}.
              {runs.data?.[0] && <> <button className="text-brand-soft hover:underline" onClick={() => nav(`/runs/${runs.data![0].source}/${runs.data![0].name}`)}>Open the latest</button>.</>}
            </Empty></Card>
          )}
        </div>
      </div>
    </div>
  )
}
