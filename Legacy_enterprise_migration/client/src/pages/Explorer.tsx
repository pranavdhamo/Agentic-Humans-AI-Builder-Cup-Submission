import { useEffect, useState } from 'react'
import { Badge, Card, Code, Empty, Spinner, Tabs } from '../components/ui'
import { api } from '../lib/api'
import { num } from '../lib/format'
import { useAsync } from '../lib/useAsync'

const PAGE = 25

function Golden({ scenario, artifact }: { scenario: string; artifact: string }) {
  const [offset, setOffset] = useState(0)
  useEffect(() => setOffset(0), [scenario, artifact])
  const g = useAsync(() => api.golden(scenario, artifact, offset, PAGE), [scenario, artifact, offset])
  if (g.error) return <Empty>{g.error}</Empty>
  const d = g.data
  return (
    <div>
      <div className="flex items-center justify-between border-b border-ink-600/40 px-4 py-2 text-xs text-slate-500">
        <span>{d ? `${num(d.total)} records x ${d.record_length} bytes` : <Spinner />}{d && d.masked.length > 0 && <> - clock fields masked in comparison: <span className="font-mono">{d.masked.join(', ')}</span></>}</span>
        <span className="flex items-center gap-2">
          <button className="btn px-2 py-0.5 text-xs" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>prev</button>
          {d ? `${offset + 1}-${Math.min(offset + PAGE, d.total)}` : ''}
          <button className="btn px-2 py-0.5 text-xs" disabled={!d || offset + PAGE >= d.total} onClick={() => setOffset(offset + PAGE)}>next</button>
        </span>
      </div>
      <div className="max-h-[520px] overflow-auto">
        <table className="w-full text-left font-mono text-[11px]">
          <thead className="sticky top-0 bg-ink-900 text-[10px] uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-3 py-2">edge case</th>
              {(d?.columns ?? []).filter((c) => c !== 'FILLER').map((c) => <th key={c} className="whitespace-nowrap px-3 py-2">{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {(d?.rows ?? []).map((r, i) => (
              <tr key={r.key + i} className="border-t border-ink-600/30 hover:bg-ink-800/60">
                <td className="max-w-[260px] px-3 py-1.5 font-sans text-xs text-warn">{r.label ?? ''}</td>
                {d!.columns.filter((c) => c !== 'FILLER').map((c) => <td key={c} className="max-w-[220px] truncate whitespace-nowrap px-3 py-1.5 text-slate-300" title={r.fields[c]}>{r.fields[c]}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Source({ program }: { program: string }) {
  const [tab, setTab] = useState<'cobol' | 'java'>('cobol')
  const [file, setFile] = useState(0)
  const cobol = useAsync(() => api.cobol(program), [program])
  const java = useAsync(() => api.java(program), [program])
  useEffect(() => setFile(0), [program, tab])

  return (
    <Card title="Side by side: COBOL and the Java port" right={<Tabs tabs={[{ id: 'cobol', label: 'COBOL' }, { id: 'java', label: 'Java (reference port)' }]} value={tab} onChange={setTab} />}>
      {tab === 'cobol' ? (
        cobol.data && !cobol.data.available ? <Empty>{cobol.data.hint}</Empty> : <Code text={cobol.data?.content ?? ''} maxHeight="max-h-[620px]" />
      ) : (
        <div>
          <div className="flex flex-wrap gap-1 border-b border-ink-600/40 px-4 py-2">
            {(java.data ?? []).map((f, i) => (
              <button key={f.path} onClick={() => setFile(i)} className={`rounded px-2 py-0.5 font-mono text-[11px] ${file === i ? 'bg-ink-700 text-fg' : 'text-slate-500 hover:text-slate-200'}`}>{f.path}</button>
            ))}
          </div>
          <Code text={java.data?.[file]?.content ?? ''} maxHeight="max-h-[620px]" />
        </div>
      )}
    </Card>
  )
}

export default function Explorer() {
  const scen = useAsync(api.scenarios, [])
  const [name, setName] = useState('')
  const [artifact, setArtifact] = useState('')
  const list = scen.data ?? []
  const current = list.find((s) => s.name === name) ?? list[0]

  useEffect(() => { if (current && current.name !== name) setName(current.name) }, [current, name])
  useEffect(() => { if (current && !current.artifacts.includes(artifact)) setArtifact(current.artifacts[0] ?? '') }, [current, artifact])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-fg">Oracle Explorer</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-400">The golden output the real COBOL produced for each scenario. This is the ground truth every migration is held to.</p>
      </div>

      {scen.loading && <Spinner />}
      <div className="grid gap-6 xl:grid-cols-[320px_1fr]">
        <Card title="Scenarios">
          <ul className="divide-y divide-ink-600/30">
            {list.map((s) => (
              <li key={s.name}>
                <button onClick={() => setName(s.name)} className={`block w-full px-4 py-3 text-left transition hover:bg-ink-800/70 ${current?.name === s.name ? 'bg-brand/10' : ''}`}>
                  <div className="flex items-center justify-between"><span className="font-mono text-sm text-fg">{s.name}</span><Badge tone={s.return_code === '16' ? 'warn' : 'mute'}>rc {s.return_code ?? '?'}</Badge></div>
                  <div className="mt-1 text-xs text-slate-500">{s.case_count ? `${s.case_count} labelled edge cases` : 'CardDemo sample data'}</div>
                  {s.case_count > 0 && <div className="mt-1.5 flex flex-wrap gap-1">{Object.entries(s.categories).slice(0, 4).map(([c, n]) => <Badge key={c}>{c} {n}</Badge>)}</div>}
                </button>
              </li>
            ))}
          </ul>
        </Card>

        <div className="space-y-6">
          {current && (
            <Card title="Golden records" right={<Tabs tabs={current.artifacts.map((a) => ({ id: a, label: a }))} value={artifact} onChange={setArtifact} />}>
              {artifact ? <Golden scenario={current.name} artifact={artifact} /> : <Empty>No artifacts.</Empty>}
            </Card>
          )}
          {current && <Source program={current.program} />}
        </div>
      </div>
    </div>
  )
}
