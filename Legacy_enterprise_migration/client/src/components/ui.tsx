import { useState, type ReactNode } from 'react'
import type { JobStatus } from '../lib/types'

export function Card({ title, right, children, className = '' }: { title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {(title || right) && (
        <div className="card-h">
          <span className="card-t">{title}</span>
          {right}
        </div>
      )}
      {children}
    </section>
  )
}

const TONES = {
  ok: 'border-ok/30 bg-ok/10 text-ok',
  bad: 'border-bad/30 bg-bad/10 text-bad',
  warn: 'border-warn/30 bg-warn/10 text-warn',
  brand: 'border-brand/30 bg-brand/10 text-brand-soft',
  mute: 'border-ink-600 bg-ink-800 text-slate-400',
} as const
export type Tone = keyof typeof TONES

export function Badge({ tone = 'mute', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${TONES[tone]}`}>{children}</span>
}

export const statusTone = (s: JobStatus | string): Tone =>
  s === 'passed' || s === 'PASS' ? 'ok' : s === 'failed' || s === 'FAIL' || s === 'error' ? 'bad' : s === 'running' || s === 'queued' ? 'brand' : 'mute'

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: Tone }) {
  const color = tone === 'ok' ? 'text-ok' : tone === 'bad' ? 'text-bad' : tone === 'warn' ? 'text-warn' : tone === 'brand' ? 'text-brand-soft' : 'text-fg'
  return (
    <div className="card px-4 py-3">
      <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${color}`}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-slate-500">{hint}</div>}
    </div>
  )
}

export function Spinner({ className = 'h-4 w-4' }: { className?: string }) {
  return <span className={`inline-block animate-spin rounded-full border-2 border-brand border-t-transparent ${className}`} aria-label="loading" />
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="p-6 text-center text-sm text-slate-500">{children}</p>
}

export function ErrorNote({ message }: { message: string | null }) {
  return message ? <div className="rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-sm text-bad">{message}</div> : null
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="flex flex-wrap gap-1">
      {tabs.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${value === t.id ? 'bg-brand/15 text-brand-soft' : 'text-slate-500 hover:text-slate-200'}`}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

export function Code({ text, maxHeight = 'max-h-[520px]', empty = 'Nothing here yet.' }: { text: string; maxHeight?: string; empty?: string }) {
  const [copied, setCopied] = useState(false)
  if (!text) return <Empty>{empty}</Empty>
  const lines = text.split('\n')
  return (
    <div className="relative">
      <button
        className="absolute right-3 top-2 z-10 rounded bg-ink-700 px-2 py-0.5 text-[10px] font-medium text-slate-300 hover:text-fg"
        onClick={() => navigator.clipboard?.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1200) })}
      >
        {copied ? 'copied' : 'copy'}
      </button>
      <pre className={`${maxHeight} overflow-auto rounded-b-xl bg-ink-950/60 py-3 font-mono text-[11.5px] leading-relaxed text-slate-300`}>
        {lines.map((l, i) => (
          <div key={i} className="flex hover:bg-ink-800/60">
            <span className="w-12 shrink-0 select-none pr-3 text-right text-slate-600">{i + 1}</span>
            <span className="whitespace-pre pr-4">{l || ' '}</span>
          </div>
        ))}
      </pre>
    </div>
  )
}

export function LogView({ lines, live }: { lines: string[]; live?: boolean }) {
  if (!lines.length) return <Empty>{live ? 'Waiting for output...' : 'No output yet. Start a job.'}</Empty>
  return (
    <div className="max-h-[360px] overflow-auto rounded-b-xl bg-ink-950/70 p-3 font-mono text-[11.5px] leading-relaxed" ref={(el) => { if (el && live) el.scrollTop = el.scrollHeight }}>
      {lines.map((l, i) => (
        <div key={i} className={l.startsWith('$') ? 'text-brand-soft' : /FAIL|ERROR|BUILD FAILED/.test(l) ? 'text-bad' : /PASS|BUILD OK/.test(l) ? 'text-ok' : 'text-slate-400'}>
          {l || ' '}
        </div>
      ))}
    </div>
  )
}

export function ProgressBar({ value, total, tone = 'brand', indeterminate }: { value: number; total: number; tone?: 'brand' | 'ok' | 'bad'; indeterminate?: boolean }) {
  const w = total > 0 ? Math.min(100, (value / total) * 100) : 0
  const bg = tone === 'ok' ? 'bg-ok' : tone === 'bad' ? 'bg-bad' : 'bg-brand'
  return (
    <div className={`relative h-1.5 w-full overflow-hidden rounded-full bg-ink-700 ${indeterminate ? 'indeterminate' : ''}`}>
      {!indeterminate && <div className={`h-full rounded-full transition-all duration-500 ${bg}`} style={{ width: `${w}%` }} />}
    </div>
  )
}
