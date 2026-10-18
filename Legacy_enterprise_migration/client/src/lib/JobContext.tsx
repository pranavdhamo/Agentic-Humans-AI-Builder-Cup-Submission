import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api } from './api'
import { useAuth } from './AuthContext'
import type { Attempt, Gate, GateDecision, Job, ScenarioResult, StepEvent, StudioEvent } from './types'

type Ev<T extends StudioEvent['type']> = Extract<StudioEvent, { type: T }>

interface JobState {
  job: Job | null
  events: StudioEvent[]
  logs: string[]
  attempts: Attempt[]
  steps: StepEvent[]
  gate: Gate | null
  decisions: GateDecision[]
  plan: string[]
  results: ScenarioResult[]
  running: string | null
  busy: boolean
  error: string | null
  start: (starter: () => Promise<Job>) => Promise<void>
  follow: (job: Job) => void
  cancel: () => Promise<void>
  answerGate: (action: 'approve' | 'stop', hint: string) => Promise<void>
}

const Ctx = createContext<JobState | null>(null)

export function JobProvider({ children }: { children: ReactNode }) {
  const { profile, project } = useAuth()
  const [job, setJob] = useState<Job | null>(null)
  const [events, setEvents] = useState<StudioEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const source = useRef<EventSource | null>(null)
  const timer = useRef<number | null>(null)

  const closeStream = useCallback(() => {
    source.current?.close()
    source.current = null
    if (timer.current) window.clearInterval(timer.current)
    timer.current = null
  }, [])

  const follow = useCallback((j: Job) => {
    closeStream()
    setJob(j)
    setEvents([])
    const es = new EventSource(api.eventsUrl(j.id))
    source.current = es
    let buffer: StudioEvent[] = []
    const flush = () => {
      if (buffer.length) {
        const chunk = buffer
        buffer = []
        setEvents((prev) => [...prev, ...chunk])
      }
    }
    timer.current = window.setInterval(flush, 120)
    es.onmessage = (m) => buffer.push(JSON.parse(m.data) as StudioEvent)
    es.addEventListener('end', async () => {
      flush()
      closeStream()
      try {
        setJob(await api.jobs().then((all) => all.find((x) => x.id === j.id) ?? j))
      } catch { /* keep the last known state */ }
    })
  }, [closeStream])

  // Re-attach to the newest job of the active project (also after a page refresh).
  const projectId = project?.id
  const userId = profile?.user.id
  useEffect(() => {
    closeStream()
    setJob(null)
    setEvents([])
    if (!userId) return
    api.jobs(projectId).then((all) => {
      const live = all.find((j) => j.status === 'running' || j.status === 'queued')
      if (live) follow(live)
      else if (all[0]) setJob(all[0])
    }).catch(() => undefined)
    return closeStream
  }, [projectId, userId, follow, closeStream])

  const start = useCallback(async (starter: () => Promise<Job>) => {
    setError(null)
    try {
      follow(await starter())
    } catch (e) {
      setError((e as Error).message)
    }
  }, [follow])

  const cancel = useCallback(async () => {
    if (job) setJob(await api.cancel(job.id))
  }, [job])

  const answerGate = useCallback(async (action: 'approve' | 'stop', hint: string) => {
    const g = [...events].reverse().find((e): e is Ev<'gate'> => e.type === 'gate')
    if (!job || !g) return
    setError(null)
    try {
      await api.answerGate(job.id, g.id, action, hint)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [job, events])

  const value = useMemo<JobState>(() => {
    const statusEv = [...events].reverse().find((e): e is Ev<'status'> => e.type === 'status')
    const live = statusEv ? statusEv.status : job?.status
    const results = events.filter((e): e is Ev<'scenario'> => e.type === 'scenario')
    const started = events.filter((e) => e.type === 'scenario_start').length
    const planEv = events.find((e): e is Ev<'plan'> => e.type === 'plan')
    const planNames = planEv ? planEv.scenarios : []
    const gates = events.filter((e): e is Ev<'gate'> => e.type === 'gate')
    const decisions = events.filter((e): e is Ev<'gate_done'> => e.type === 'gate_done')
    const lastGate = gates[gates.length - 1]
    const open = lastGate && !decisions.some((d) => d.id === lastGate.id) && live === 'running' ? lastGate : null
    return {
      job: job && live ? { ...job, status: live } : job,
      events,
      logs: events.filter((e): e is Ev<'log'> => e.type === 'log').map((e) => e.line),
      attempts: events.filter((e): e is Ev<'attempt'> => e.type === 'attempt'),
      steps: events.filter((e): e is Ev<'step'> => e.type === 'step'),
      gate: open,
      decisions,
      plan: planNames,
      results,
      running: started > results.length ? planNames[results.length] ?? null : null,
      busy: live === 'running' || live === 'queued',
      error, start, follow, cancel, answerGate,
    }
  }, [events, job, error, start, follow, cancel, answerGate])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useJob(): JobState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useJob outside JobProvider')
  return v
}
