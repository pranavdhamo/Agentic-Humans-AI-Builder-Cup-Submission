const STEPS = [
  { t: 'COBOL oracle', d: 'real program on GnuCOBOL, golden output', tone: 'border-warn/40 text-warn' },
  { t: 'Gemini migrate', d: 'COBOL + copybooks to Spring Batch', tone: 'border-brand/50 text-brand-soft' },
  { t: 'Build', d: 'Maven compiles the candidate', tone: 'border-slate-500/40 text-slate-300' },
  { t: 'Verify', d: 'field-level diff vs golden', tone: 'border-ok/40 text-ok' },
  { t: 'Repair', d: 'mismatches go back to the model', tone: 'border-bad/40 text-bad' },
]

export default function PipelineDiagram({ active }: { active?: number }) {
  return (
    <ol className="flex flex-wrap items-stretch gap-2 p-4">
      {STEPS.map((s, i) => (
        <li key={s.t} className="flex items-center gap-2">
          <div className={`min-w-[150px] rounded-lg border bg-ink-800/70 px-3 py-2 ${s.tone} ${active === i ? 'shadow-glow ring-1 ring-brand' : ''}`}>
            <div className="text-xs font-semibold">{i + 1}. {s.t}</div>
            <div className="text-[11px] text-slate-500">{s.d}</div>
          </div>
          {i < STEPS.length - 1 && <span className="text-slate-600">{i === 3 ? '↺' : '→'}</span>}
        </li>
      ))}
    </ol>
  )
}
