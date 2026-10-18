import { Fragment, useState } from 'react'
import { Badge, Card, Empty, ErrorNote, LogView, ProgressBar, Spinner, Stat, statusTone } from '../components/ui'
import { api } from '../lib/api'
import { num, pct } from '../lib/format'
import { useAuth } from '../lib/AuthContext'
import { useJob } from '../lib/JobContext'
import { useAsync } from '../lib/useAsync'
import type { ScenarioResult } from '../lib/types'

function Detail({ r }: { r: ScenarioResult }) {
  const arts = r.report.artifacts ?? []
  return (
    <div className="space-y-3 bg-ink-950/40 px-4 py-3 text-xs">
      <div className="flex flex-wrap gap-2">
        <Badge tone={r.report.return_code_matches === false ? 'bad' : 'ok'}>return code {r.report.return_code_matches === false ? 'differs' : 'matches'}</Badge>
        <Badge tone={r.report.counters_match === false ? 'bad' : 'ok'}>console counters {r.report.counters_match === false ? 'differ' : 'match'}</Badge>
        <Badge>{r.seconds}s</Badge>
      </div>
      <table className="w-full text-left">
        <thead className="text-[10px] uppercase tracking-wider text-slate-500"><tr><th className="py-1 pr-4">Artifact</th><th className="pr-4">Status</th><th>Records identical</th></tr></thead>
        <tbody>
          {arts.map((a) => (
            <tr key={a.artifact} className="border-t border-ink-600/30">
              <td className="py-1.5 pr-4 font-mono text-slate-200">{a.artifact}</td>
              <td className="pr-4"><Badge tone={a.status === 'IDENTICAL' ? 'ok' : 'bad'}>{a.status}</Badge></td>
              <td className="tabular-nums">{a.matched}/{a.golden_records ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {arts.flatMap((a) => a.mismatches.slice(0, 3).map((m) => (
        <div key={a.artifact + m.key} className="rounded border border-bad/20 bg-bad/5 px-2 py-1.5 font-mono text-[11px] text-bad">
          {a.artifact} key {m.key}: {m.problem ?? (m.diffs ?? []).slice(0, 2).map((d) => `${d.field} expected '${d.expected}' got '${d.actual}'`).join('; ')}
        </div>
      )))}
      {r.crashed && r.console && <pre className="rounded bg-ink-950 p-2 font-mono text-[11px] text-bad">{r.console}</pre>}
    </div>
  )
}

export default function Verifier() {
  const { project, can } = useAuth()
  const scen = useAsync(api.scenarios, [])
  const { start, busy, job, plan, results, running, logs, error } = useJob()
  const [open, setOpen] = useState<string | null>(null)
  const isVerify = job?.kind === 'verify'
  const all = scen.data ?? []
  const names = plan.length ? plan : all.map((s) => s.name)
  const byName = new Map(isVerify ? results.map((r) => [r.name, r]) : [])
  const totalRec = [...byName.values()].reduce((a, r) => a + r.records_total, 0)
  const okRec = [...byName.values()].reduce((a, r) => a + r.records_matched, 0)
  const passed = [...byName.values()].filter((r) => r.passed).length
  const failed = byName.size - passed

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-fg">Verifier</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-400">Runs the Java ports on every scenario and diffs each output record, field by field, against the golden output captured from the real COBOL. No model is involved.</p>
        </div>
        <div className="flex gap-2">
          <button className="btn" disabled={busy || !can('can_run_build')} onClick={() => void start(api.startBuild)}>Rebuild Java</button>
          <button className="btn" disabled={busy || !can('can_run_mutation')} onClick={() => void start(api.startMutation)} title="Breaks the port 27 ways; every break must be caught">Mutation check</button>
          <button className="btn btn-primary" disabled={busy || !can('can_run_verifier')} onClick={() => void start(() => api.startVerify(project?.id))}>{busy && isVerify ? <><Spinner /> Verifying</> : 'Run all scenarios'}</button>
        </div>
      </div>
      <ErrorNote message={error} />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Scenarios" value={`${passed}/${names.length}`} hint="passing" tone={isVerify && !busy && failed === 0 && passed > 0 ? 'ok' : failed ? 'bad' : undefined} />
        <Stat label="Records identical" value={totalRec ? pct(okRec, totalRec) : '-'} hint={totalRec ? `${num(okRec)} / ${num(totalRec)}` : 'run to see'} tone={totalRec && okRec === totalRec ? 'ok' : undefined} />
        <Stat label="Verdict" value={isVerify && !busy && byName.size ? (failed ? 'FAIL' : 'PASS') : busy && isVerify ? 'running' : '-'} tone={isVerify && !busy && byName.size ? (failed ? 'bad' : 'ok') : 'brand'} />
        <Stat label="Last job" value={job ? job.kind : '-'} hint={job?.status} />
      </div>

      <Card title="Scenario matrix" right={busy && isVerify ? <div className="w-40"><ProgressBar value={byName.size} total={names.length} /></div> : undefined}>
        <table className="w-full text-left text-sm">
          <thead className="text-[10px] uppercase tracking-wider text-slate-500">
            <tr className="border-b border-ink-600/60">
              {['Scenario', 'Program', 'Edge cases', 'Records', 'Verdict'].map((h) => <th key={h} className="px-4 py-2 font-medium">{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {names.map((n) => {
              const info = all.find((s) => s.name === n)
              const r = byName.get(n)
              return (
                <Fragment key={n}>
                  <tr className={`border-b border-ink-600/30 ${r ? 'cursor-pointer hover:bg-ink-800/60' : ''}`} onClick={() => r && setOpen(open === n ? null : n)}>
                    <td className="px-4 py-2.5 font-mono text-xs text-fg">{n}</td>
                    <td className="px-4 py-2.5 text-slate-400">{info?.program}</td>
                    <td className="px-4 py-2.5 tabular-nums text-slate-400">{info?.case_count ?? '-'}</td>
                    <td className="px-4 py-2.5 tabular-nums text-slate-300">{r ? `${num(r.records_matched)}/${num(r.records_total)}` : '-'}</td>
                    <td className="px-4 py-2.5">
                      {r ? <Badge tone={statusTone(r.passed ? 'PASS' : 'FAIL')}>{r.passed ? 'PASS' : 'FAIL'}</Badge>
                        : running === n ? <Badge tone="brand"><Spinner className="h-3 w-3" /> running</Badge> : <Badge>pending</Badge>}
                    </td>
                  </tr>
                  {open === n && r && <tr><td colSpan={5} className="p-0"><Detail r={r} /></td></tr>}
                </Fragment>
              )
            })}
          </tbody>
        </table>
        {!names.length && <Empty>No scenarios found.</Empty>}
      </Card>

      <Card title="Job output"><LogView lines={logs} live={busy} /></Card>
    </div>
  )
}
