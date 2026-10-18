import { useEffect, useState } from 'react'
import { useAuth } from '../lib/AuthContext'
import { useJob } from '../lib/JobContext'
import { Badge, Code } from './ui'

/** The run is paused here until a reviewer approves, adds guidance for the model, or stops it. */
export default function HumanGate() {
  const { gate, answerGate } = useJob()
  const { can } = useAuth()
  const [hint, setHint] = useState('')
  const [showDetail, setShowDetail] = useState(false)
  const [sending, setSending] = useState(false)
  useEffect(() => { setHint(''); setShowDetail(false); setSending(false) }, [gate?.id])

  if (!gate) return null
  const allowed = can('can_approve_gates')
  const send = async (action: 'approve' | 'stop') => {
    setSending(true)
    await answerGate(action, hint)
  }

  return (
    <div className="card border-warn/50 shadow-glow">
      <div className="card-h">
        <span className="card-t text-warn">{'✋'} Human review needed</span>
        <Badge tone="warn">{gate.point === 'generate' ? 'before generation' : `before repair ${gate.iteration}`}</Badge>
      </div>
      <div className="space-y-3 p-4">
        <p className="text-sm text-slate-300">{gate.summary}</p>
        {gate.detail && (
          <div>
            <button className="text-xs text-brand-soft hover:underline" onClick={() => setShowDetail((v) => !v)}>{showDetail ? 'hide' : 'show'} verifier feedback</button>
            {showDetail && <div className="mt-2 overflow-hidden rounded-lg border border-ink-600"><Code text={gate.detail} maxHeight="max-h-56" /></div>}
          </div>
        )}
        {allowed ? (
          <>
            <div>
              <label className="label" htmlFor="hint">Guidance for the model (optional)</label>
              <textarea id="hint" className="input h-20 resize-y" value={hint} maxLength={4000} onChange={(e) => setHint(e.target.value)}
                placeholder="e.g. COBOL truncates, it does not round; check the order of the over-limit and expiry checks." />
            </div>
            <div className="flex flex-wrap gap-2">
              <button className="btn btn-primary" disabled={sending} onClick={() => void send('approve')}>{hint.trim() ? 'Approve with guidance' : 'Approve and continue'}</button>
              <button className="btn btn-danger" disabled={sending} onClick={() => void send('stop')}>Stop the run</button>
            </div>
          </>
        ) : (
          <p className="rounded-lg border border-ink-600 bg-ink-800 px-3 py-2 text-sm text-slate-400">
            Waiting for a reviewer. Your role cannot approve gates; a senior developer, lead architect or project admin on this project can.
          </p>
        )}
      </div>
    </div>
  )
}
