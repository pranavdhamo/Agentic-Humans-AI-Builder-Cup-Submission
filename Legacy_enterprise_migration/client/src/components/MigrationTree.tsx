import type { ReactNode } from 'react'
import type { Gate, GateDecision, StepEvent, StudioEvent } from '../lib/types'
import { num } from '../lib/format'

type State = 'pending' | 'running' | 'ok' | 'fail' | 'waiting'

const RING: Record<State, string> = {
  pending: 'border-ink-600 text-slate-500 border-dashed',
  running: 'border-brand text-brand-soft shadow-glow',
  ok: 'border-ok/50 text-ok bg-ok/5',
  fail: 'border-bad/50 text-bad bg-bad/5',
  waiting: 'border-warn/60 text-warn bg-warn/10 shadow-glow',
}

function Node({ state, title, sub, kind = 'step' }: { state: State; title: string; sub?: ReactNode; kind?: 'step' | 'decision' | 'leaf' | 'gate' }) {
  const shape = kind === 'decision' ? 'rounded-full px-3' : kind === 'leaf' ? 'rounded-xl px-3 font-semibold' : 'rounded-lg px-2.5'
  return (
    <div className={`flex min-w-[84px] flex-col justify-center border bg-ink-900 py-1.5 text-center transition ${shape} ${RING[state]} ${state === 'running' ? 'animate-pulse' : ''}`}>
      <div className="flex items-center justify-center gap-1.5 text-[11px] font-semibold">
        {kind === 'gate' && <span aria-hidden>{'✋'}</span>}
        {state === 'running' && <span className="h-2 w-2 animate-ping rounded-full bg-brand" />}
        {title}
      </div>
      {sub && <div className="text-[10px] font-normal text-slate-500">{sub}</div>}
    </div>
  )
}

function Arrow({ label, tone }: { label?: string; tone?: 'ok' | 'bad' }) {
  return (
    <div className="flex min-w-[22px] flex-col items-center text-slate-600">
      {label && <span className={`text-[9px] font-semibold uppercase ${tone === 'ok' ? 'text-ok' : tone === 'bad' ? 'text-bad' : 'text-slate-500'}`}>{label}</span>}
      <span className="leading-none">{'→'}</span>
    </div>
  )
}

interface Row {
  i: number
  gate?: { state: State; hint: string; by: string | null; action?: string; point: string }
  llm: State; llmTokens?: number
  build: State
  compiles: State
  verify: State; verifySub?: string
  match: State
  leaf?: 'pass' | 'exhausted' | 'stopped'
}

function derive(events: StudioEvent[], busy: boolean, gatePoints: string[]): Row[] {
  const steps = events.filter((e): e is Extract<StudioEvent, { type: 'step' }> => e.type === 'step') as (StepEvent & { type: 'step' })[]
  const gates = events.filter((e): e is Extract<StudioEvent, { type: 'gate' }> => e.type === 'gate') as (Gate & { type: 'gate' })[]
  const done = events.filter((e): e is Extract<StudioEvent, { type: 'gate_done' }> => e.type === 'gate_done') as (GateDecision & { type: 'gate_done' })[]
  const last = Math.max(-1, ...steps.map((s) => s.iteration), ...gates.map((g) => g.iteration))
  const rows: Row[] = []
  for (let i = 0; i <= last; i++) {
    const of = (kind: string) => steps.filter((s) => s.iteration === i && s.kind === kind)
    const stateOf = (kind: string): State => {
      const l = of(kind)
      if (!l.length) return 'pending'
      const d = l.find((s) => s.state === 'done')
      if (!d) return 'running'
      return kind === 'build' ? (d.ok ? 'ok' : 'fail') : kind === 'verify' ? (d.passed === d.total ? 'ok' : 'fail') : 'ok'
    }
    const dec = of('decision')[0]
    const vDone = of('verify').find((s) => s.state === 'done')
    const g = gates.find((x) => x.iteration === i)
    const gd = g ? done.find((d) => d.id === g.id) : undefined
    const build = stateOf('build')
    const row: Row = {
      i,
      llm: stateOf('llm'), llmTokens: (of('llm').find((s) => s.state === 'done')?.output_tokens),
      build,
      compiles: build === 'pending' || build === 'running' ? 'pending' : build === 'ok' ? 'ok' : 'fail',
      verify: stateOf('verify'),
      verifySub: vDone ? `${vDone.passed}/${vDone.total} scenarios` : undefined,
      match: !dec ? 'pending' : dec.outcome === 'pass' ? 'ok' : 'fail',
    }
    if (g) row.gate = { state: gd ? (gd.action === 'stop' ? 'fail' : 'ok') : busy ? 'waiting' : 'pending', hint: gd?.hint ?? '', by: gd?.by ?? null, action: gd?.action, point: g.point }
    else if (gatePoints.includes(i === 0 ? 'generate' : 'repair') && busy && i === last + 0 && !of('llm').length) row.gate = { state: 'waiting', hint: '', by: null, point: i === 0 ? 'generate' : 'repair' }
    if (dec?.outcome === 'pass') row.leaf = 'pass'
    else if (dec?.outcome === 'exhausted') row.leaf = 'exhausted'
    else if (gd?.action === 'stop') row.leaf = 'stopped'
    rows.push(row)
  }
  return rows
}

export default function MigrationTree({ events, busy, maxRepairs, gatePoints }: { events: StudioEvent[]; busy: boolean; maxRepairs: number; gatePoints: string[] }) {
  const rows = derive(events, busy, gatePoints)
  const finished = rows.length > 0 && !!rows[rows.length - 1].leaf
  const showNext = busy && !finished && rows.length > 0 && rows.length <= maxRepairs

  if (!rows.length) {
    return (
      <div className="p-6 text-center text-sm text-slate-500">
        {busy ? 'Starting the first attempt...' : 'The decision tree grows here as the migration runs: generate, build, verify, then repair or finish.'}
      </div>
    )
  }

  return (
    <div className="space-y-0 overflow-x-auto p-4">
      {rows.map((r, idx) => (
        <div key={r.i} className="relative">
          <div className="flex items-center gap-1 py-2">
            <div className="w-14 shrink-0 text-[10px] font-semibold uppercase leading-tight tracking-wider text-slate-500">{r.i === 0 ? 'attempt 1' : `repair ${r.i}`}</div>
            {r.gate && (
              <>
                <div title={r.gate.hint ? `Reviewer hint: ${r.gate.hint}` : undefined}>
                  <Node kind="gate" state={r.gate.state} title="Human review"
                    sub={r.gate.state === 'waiting' ? 'waiting for you' : r.gate.action === 'stop' ? `stopped${r.gate.by ? ' by ' + r.gate.by : ''}` : r.gate.hint ? 'approved + hint' : 'approved'} />
                </div>
                <Arrow />
              </>
            )}
            <Node state={r.llm} title={r.i === 0 ? 'Generate' : 'Repair'} sub={r.llmTokens ? `${num(r.llmTokens)} tok out` : undefined} />
            <Arrow />
            <Node state={r.build} title="Build" sub="maven" />
            <Arrow />
            <Node kind="decision" state={r.compiles} title="Compiles?" sub={r.compiles === 'pending' ? '' : r.compiles === 'ok' ? 'yes' : 'no'} />
            <Arrow label="yes" tone="ok" />
            <Node state={r.verify} title="Verify" sub={r.verifySub ?? 'vs oracle'} />
            <Arrow />
            <Node kind="decision" state={r.match} title="All match?" sub={r.match === 'pending' ? '' : r.match === 'ok' ? 'yes' : 'no'} />
            {r.leaf === 'pass' && <><Arrow label="yes" tone="ok" /><Node kind="leaf" state="ok" title="PASS" sub="= COBOL" /></>}
            {r.leaf === 'exhausted' && <><Arrow label="no" tone="bad" /><Node kind="leaf" state="fail" title="Out of repairs" /></>}
            {r.leaf === 'stopped' && <><Arrow /><Node kind="leaf" state="fail" title="Stopped" sub="by reviewer" /></>}
          </div>
          {(idx < rows.length - 1 || showNext) && (
            <div className="ml-[64px] flex h-5 items-center gap-2 border-l-2 border-dashed border-ink-600 pl-3 text-[10px] font-semibold uppercase text-bad">
              {'↳'} no: feed the field-level mismatches back
            </div>
          )}
        </div>
      ))}
      {showNext && (
        <div className="flex items-center gap-1 py-2 opacity-60">
          <div className="w-16 shrink-0 text-[10px] font-semibold uppercase tracking-wider text-slate-500">repair {rows.length}</div>
          <Node state="pending" title="Repair" sub="not started" />
        </div>
      )}
    </div>
  )
}
