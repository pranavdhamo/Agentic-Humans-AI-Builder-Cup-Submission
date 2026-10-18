import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import ReactFlow, {
  addEdge, Background, ConnectionMode, Controls, Handle, MarkerType, MiniMap, Position, ReactFlowProvider,
  useEdgesState, useNodesState, type Connection, type Edge, type Node, type NodeProps,
} from 'reactflow'
import 'reactflow/dist/style.css'
import HumanGate from '../components/HumanGate'
import { Badge, Card, ErrorNote, Spinner } from '../components/ui'
import { api } from '../lib/api'
import { useAuth } from '../lib/AuthContext'
import { useJob } from '../lib/JobContext'
import type { BoardGraph, Compiled, StudioEvent } from '../lib/types'

type State = 'idle' | 'running' | 'ok' | 'fail' | 'waiting'
type NodeData = Record<string, unknown>

const KIND: Record<string, { label: string; tag: string; bar: string; hint: string }> = {
  source: { label: 'COBOL Source', tag: 'SRC', bar: 'bg-warn', hint: 'Which legacy program to port' },
  generator: { label: 'Code Generator', tag: 'GEN', bar: 'bg-brand', hint: 'Gemini writes the Java port' },
  build: { label: 'Build', tag: 'MVN', bar: 'bg-slate-400', hint: 'Maven compiles the candidate' },
  verify: { label: 'Verifier', tag: 'VER', bar: 'bg-ok', hint: 'Diff every record vs the COBOL oracle' },
  repair: { label: 'Repair Loop', tag: 'FIX', bar: 'bg-bad', hint: 'Send mismatches back to the model' },
  gate: { label: 'Human Review Gate', tag: 'HUM', bar: 'bg-warn', hint: 'Pause until a reviewer approves' },
  done: { label: 'Result', tag: 'END', bar: 'bg-ok', hint: 'Pass or fail verdict' },
}
const RING: Record<State, string> = {
  idle: 'border-ink-600', running: 'border-brand shadow-glow', ok: 'border-ok/60', fail: 'border-bad/60', waiting: 'border-warn shadow-glow',
}

interface Ctx { statusOf: (id: string, type: string, data: NodeData) => State; allowed: Set<string>; locked: boolean }
const BoardCtx = createContext<Ctx>({ statusOf: () => 'idle', allowed: new Set(), locked: true })

function summary(type: string, d: NodeData): string {
  if (type === 'source') return String(d.program ?? 'choose a program')
  if (type === 'generator') return `${d.provider ?? 'mock'}${d.provider === 'gemini' ? ` - ${d.model ?? ''}` : ''} - ${d.mode ?? 'guided'}`
  if (type === 'repair') return `up to ${d.max_repairs ?? 4} repairs`
  if (type === 'gate') return `${d.enabled === false ? 'off' : 'on'} - ${d.point === 'generate' ? 'before generation' : 'before each repair'}`
  return KIND[type]?.hint ?? ''
}

function AgentNode({ id, type, data, selected }: NodeProps<NodeData>) {
  const { statusOf, allowed } = useContext(BoardCtx)
  const k = KIND[type] ?? KIND.build
  const st = statusOf(id, type, data)
  const locked = !allowed.has(type)
  const handle = '!h-2.5 !w-2.5 !border-2 !border-ink-900 !bg-brand'
  return (
    <div className={`relative w-52 rounded-xl border bg-ink-900 shadow-lg transition ${RING[st]} ${selected ? 'ring-2 ring-brand/60' : ''} ${locked ? 'opacity-70' : ''}`}>
      <span className={`absolute inset-x-0 top-0 h-1 rounded-t-xl ${k.bar}`} />
      {(['l', 'r', 't', 'b'] as const).map((h) => (
        <Handle key={h} id={h} type="source" position={{ l: Position.Left, r: Position.Right, t: Position.Top, b: Position.Bottom }[h]} className={handle} />
      ))}
      <div className="px-3 pb-2.5 pt-3">
        <div className="flex items-center justify-between">
          <span className="rounded border border-ink-600 bg-ink-800 px-1.5 py-0.5 text-[9px] font-bold tracking-wider text-slate-400">{k.tag}</span>
          <span className="flex items-center gap-1.5 text-[10px] font-medium text-slate-500">
            {st === 'running' && <span className="h-2.5 w-2.5 animate-spin rounded-full border-2 border-brand border-t-transparent" />}
            {st === 'waiting' && <span>{'✋'} waiting</span>}
            {st === 'ok' && <span className="text-ok">done</span>}
            {st === 'fail' && <span className="text-bad">failed</span>}
            {locked && <span title="Your role cannot use this agent">{'🔒'}</span>}
          </span>
        </div>
        <div className="mt-1.5 text-sm font-semibold text-fg">{k.label}</div>
        <div className="truncate text-[11px] text-slate-500" title={summary(type, data)}>{summary(type, data)}</div>
      </div>
    </div>
  )
}
const nodeTypes = Object.fromEntries(Object.keys(KIND).map((k) => [k, AgentNode]))

function toFlow(g: BoardGraph): { nodes: Node<NodeData>[]; edges: Edge[] } {
  return {
    nodes: g.nodes.map((n) => ({ id: n.id, type: n.type, position: n.position, data: n.data })),
    edges: g.edges.map((e) => styleEdge({ ...e })),
  }
}
function styleEdge(e: Edge): Edge {
  return {
    ...e, type: 'smoothstep', animated: false,
    style: { stroke: 'rgb(var(--s500))', strokeWidth: 1.6 },
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgb(var(--s500))' },
    labelStyle: { fill: 'rgb(var(--s300))', fontSize: 10, fontWeight: 600 },
    labelBgStyle: { fill: 'rgb(var(--ink-900))' },
    labelBgPadding: [5, 2], labelBgBorderRadius: 5,
  }
}
function fromFlow(nodes: Node<NodeData>[], edges: Edge[]): BoardGraph {
  return {
    nodes: nodes.map((n) => ({ id: n.id, type: n.type ?? 'build', position: { x: Math.round(n.position.x), y: Math.round(n.position.y) }, data: n.data })),
    edges: edges.map((e) => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle, targetHandle: e.targetHandle, label: typeof e.label === 'string' ? e.label : undefined })),
  }
}

/** Live status of a board node from the migration job's events. */
function liveStatus(events: StudioEvent[], busy: boolean, type: string, data: NodeData): State {
  if (!events.length) return 'idle'
  const steps = events.filter((e): e is Extract<StudioEvent, { type: 'step' }> => e.type === 'step')
  const lastOf = (kind: string, pred: (i: number) => boolean = () => true) => [...steps].reverse().find((s) => s.kind === kind && pred(s.iteration))
  if (type === 'source') return steps.length || busy ? 'ok' : 'idle'
  if (type === 'gate') {
    const gates = events.filter((e): e is Extract<StudioEvent, { type: 'gate' }> => e.type === 'gate').filter((g) => g.point === data.point)
    const g = gates[gates.length - 1]
    if (!g) return 'idle'
    const d = events.find((e): e is Extract<StudioEvent, { type: 'gate_done' }> => e.type === 'gate_done' && e.id === g.id)
    return !d ? (busy ? 'waiting' : 'idle') : d.action === 'stop' ? 'fail' : 'ok'
  }
  const pick = type === 'generator' ? lastOf('llm', (i) => i === 0) : type === 'repair' ? lastOf('llm', (i) => i > 0) : type === 'build' ? lastOf('build') : type === 'verify' ? lastOf('verify') : undefined
  if (type === 'done') {
    const dec = [...steps].reverse().find((s) => s.kind === 'decision')
    return !dec ? 'idle' : dec.outcome === 'pass' ? 'ok' : dec.outcome === 'exhausted' ? 'fail' : 'idle'
  }
  if (!pick) return 'idle'
  if (pick.state === 'start') return 'running'
  if (type === 'build') return pick.ok ? 'ok' : 'fail'
  if (type === 'verify') return pick.passed === pick.total ? 'ok' : 'fail'
  return 'ok'
}

function Inspector({ node, onChange, canEdit }: { node: Node<NodeData> | undefined; onChange: (d: NodeData) => void; canEdit: boolean }) {
  const { profile } = useAuth()
  if (!node) return <p className="p-4 text-sm text-slate-500">Select a node to configure it. Drag from any handle to wire nodes together.</p>
  const k = KIND[node.type ?? 'build']
  const d = node.data
  const pol = profile!.policy
  const set = (patch: NodeData) => onChange({ ...d, ...patch })
  const tierRank = { none: 0, basic: 1, advanced: 2 }
  const models = profile!.provider.models.filter((m) => tierRank[m.tier] <= tierRank[pol.model_tier])
  const dis = !canEdit
  return (
    <div className="space-y-3 p-4">
      <div><div className="text-sm font-semibold text-fg">{k.label}</div><div className="text-xs text-slate-500">{k.hint}</div></div>
      {node.type === 'source' && (
        <div><label className="label" htmlFor="prog">Program</label>
          <select id="prog" className="input" disabled={dis} value={String(d.program ?? '')} onChange={(e) => set({ program: e.target.value })}>
            <option value="posttran">CBTRN02C - transaction posting</option><option value="intcalc">CBACT04C - interest calculation</option>
          </select></div>
      )}
      {node.type === 'generator' && (
        <>
          <div><label className="label" htmlFor="prov">Provider</label>
            <select id="prov" className="input" disabled={dis} value={String(d.provider ?? 'mock')} onChange={(e) => set({ provider: e.target.value })}>
              <option value="mock">mock (scripted)</option>
              <option value="gemini" disabled={!pol.providers.includes('gemini')}>gemini{pol.providers.includes('gemini') ? '' : ' (not for your role)'}</option>
            </select></div>
          {d.provider === 'gemini' && (
            <div><label className="label" htmlFor="mdl">Model</label>
              <select id="mdl" className="input font-mono" disabled={dis} value={String(d.model ?? '')} onChange={(e) => set({ model: e.target.value })}>
                {models.map((m) => <option key={m.id} value={m.id}>{m.id} ({m.tier})</option>)}
              </select></div>
          )}
          <div><label className="label" htmlFor="md">Prompt mode</label>
            <select id="md" className="input" disabled={dis} value={String(d.mode ?? 'guided')} onChange={(e) => set({ mode: e.target.value })}>
              {pol.modes.map((m) => <option key={m} value={m}>{m}</option>)}
            </select></div>
        </>
      )}
      {node.type === 'repair' && (
        <div><label className="label" htmlFor="mr">Max repairs (your cap {pol.max_repairs})</label>
          <input id="mr" className="input" type="number" min={0} max={pol.max_repairs} disabled={dis} value={Number(d.max_repairs ?? 4)}
            onChange={(e) => set({ max_repairs: Math.max(0, Math.min(pol.max_repairs, Number(e.target.value) || 0)) })} /></div>
      )}
      {node.type === 'gate' && (
        <>
          <div><label className="label" htmlFor="gp">Pauses the run</label>
            <select id="gp" className="input" disabled={dis} value={String(d.point ?? 'repair')} onChange={(e) => set({ point: e.target.value })}>
              <option value="generate">before the first generation</option><option value="repair">before each repair</option>
            </select></div>
          <label className="flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" disabled={dis} checked={d.enabled !== false} onChange={(e) => set({ enabled: e.target.checked })} /> gate enabled</label>
          <p className="text-xs text-slate-500">Reviewers (senior developer and above) approve, add guidance for the model, or stop the run.</p>
        </>
      )}
      {['build', 'verify', 'done'].includes(node.type ?? '') && <p className="text-xs text-slate-500">No settings. This step always runs as wired.</p>}
    </div>
  )
}

function Board() {
  const { profile, project, can } = useAuth()
  const { start, events, busy, job, error } = useJob()
  const [nodes, setNodes, onNodesChange] = useNodesState<NodeData>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [compiled, setCompiled] = useState<Compiled | null>(null)
  const [editable, setEditable] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const seq = useRef(0)

  const allowed = useMemo(() => new Set(profile!.policy.agents), [profile])
  const isBoardJob = job?.kind === 'migrate'
  const statusOf = useCallback((_id: string, type: string, data: NodeData) => (isBoardJob ? liveStatus(events, busy, type, data) : 'idle'), [events, busy, isBoardJob])

  useEffect(() => {
    if (!project) return
    setLoading(true)
    api.board(project.id).then((b) => {
      const f = toFlow(b.graph)
      setNodes(f.nodes); setEdges(f.edges); setCompiled(b.compiled); setEditable(b.editable && can('can_edit_board')); setDirty(false); setSelected(null)
    }).catch((e: Error) => setErr(e.message)).finally(() => setLoading(false))
  }, [project, setNodes, setEdges, can])

  // Re-validate (server side, with this role's agent rights) shortly after every edit.
  useEffect(() => {
    if (!project || loading) return
    const t = window.setTimeout(() => { api.validateBoard(project.id, fromFlow(nodes, edges)).then(setCompiled).catch(() => undefined) }, 350)
    return () => window.clearTimeout(t)
  }, [nodes, edges, project, loading])

  const touch = () => { setDirty(true); setMsg(null) }
  const onConnect = (c: Connection) => { if (!editable) return; setEdges((es) => addEdge(styleEdge({ ...c, id: `e_${Date.now().toString(36)}` } as Edge), es)); touch() }
  const sel = nodes.find((n) => n.id === selected)

  const add = (type: string) => {
    if (!editable) return
    const id = `${type}_${(seq.current++).toString(36)}${Date.now().toString(36).slice(-3)}`
    const base: NodeData = type === 'source' ? { program: 'posttran' } : type === 'generator' ? { provider: 'mock', model: profile!.provider.default_model, mode: 'guided' }
      : type === 'repair' ? { max_repairs: Math.min(4, profile!.policy.max_repairs) } : type === 'gate' ? { point: 'repair', enabled: true } : {}
    setNodes((ns) => [...ns, { id, type, position: { x: 80 + ns.length * 18, y: 460 + ns.length * 8 }, data: base }])
    touch()
  }

  const save = async () => {
    if (!project) return
    setErr(null)
    try { const r = await api.saveBoard(project.id, fromFlow(nodes, edges)); setCompiled(r.compiled); setDirty(false); setMsg('Board saved for the whole project.') } catch (e) { setErr((e as Error).message) }
  }
  const reset = async () => {
    if (!project) return
    const b = await api.board(project.id)
    const f = toFlow(b.graph); setNodes(f.nodes); setEdges(f.edges); setDirty(false); setMsg('Reverted to the saved board.')
  }
  const run = () => project && void start(() => api.runBoard(project.id, fromFlow(nodes, edges)))

  const ctx = useMemo<Ctx>(() => ({ statusOf, allowed, locked: !editable }), [statusOf, allowed, editable])
  const p = compiled?.params as Record<string, unknown> | null

  return (
    <div className="space-y-4">
      <HumanGate />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {profile!.agents.map((a) => (
            <button key={a.id} className="chip disabled:opacity-40" disabled={!a.allowed || !editable} onClick={() => add(a.id)}
              title={!a.allowed ? 'Your role cannot use this agent' : !editable ? 'Your role cannot edit the board' : `Add ${a.label}`}>
              {!a.allowed && '🔒 '}+ {a.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          {!editable && <Badge tone="warn">view only for your role</Badge>}
          {dirty && <Badge tone="brand">unsaved changes</Badge>}
          <button className="btn" onClick={() => void reset()} disabled={!dirty}>Revert</button>
          <button className="btn" onClick={() => void save()} disabled={!editable || !dirty}>Save board</button>
          <button className="btn btn-primary" onClick={run} disabled={busy || !compiled?.ok || !project}>{busy && isBoardJob ? <><Spinner /> Running</> : 'Run this board'}</button>
        </div>
      </div>
      <ErrorNote message={err ?? error} />
      {msg && <div className="rounded-lg border border-ok/30 bg-ok/10 px-3 py-2 text-sm text-ok">{msg}</div>}

      <div className="grid gap-4 2xl:grid-cols-[1fr_320px]">
        <div className="card h-[560px] overflow-hidden">
          <BoardCtx.Provider value={ctx}>
            <ReactFlow
              nodes={nodes} edges={edges} nodeTypes={nodeTypes} connectionMode={ConnectionMode.Loose}
              onNodesChange={(c) => { onNodesChange(c); if (editable && c.some((x) => x.type === 'position' && x.dragging === false)) touch() }}
              onEdgesChange={(c) => { onEdgesChange(c); if (editable && c.some((x) => x.type === 'remove')) touch() }}
              onConnect={onConnect} onNodeClick={(_, n) => setSelected(n.id)} onPaneClick={() => setSelected(null)}
              nodesDraggable={editable} nodesConnectable={editable} elementsSelectable
              deleteKeyCode={editable ? ['Backspace', 'Delete'] : null}
              fitView fitViewOptions={{ padding: 0.15 }} minZoom={0.3} maxZoom={1.6} proOptions={{ hideAttribution: true }}
            >
              <Background gap={22} size={1.3} color="rgb(var(--ink-600))" />
              <Controls showInteractive={false} />
              <MiniMap pannable zoomable maskColor="rgb(var(--ink-950) / 0.7)" nodeColor="rgb(var(--brand))" />
            </ReactFlow>
          </BoardCtx.Provider>
        </div>

        <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-1 2xl:content-start">
          <Card title="Node settings"><Inspector node={sel} canEdit={editable} onChange={(d) => { setNodes((ns) => ns.map((n) => (n.id === selected ? { ...n, data: d } : n))); touch() }} /></Card>
          <Card title="Compiled plan" right={compiled && <Badge tone={compiled.ok ? 'ok' : 'bad'}>{compiled.ok ? 'valid' : 'fix wiring'}</Badge>}>
            <div className="space-y-2 p-4 text-sm">
              {compiled?.errors.map((e) => <div key={e} className="rounded border border-bad/30 bg-bad/10 px-2 py-1 text-xs text-bad">{e}</div>)}
              {compiled?.warnings.map((e) => <div key={e} className="rounded border border-warn/30 bg-warn/10 px-2 py-1 text-xs text-warn">{e}</div>)}
              {p && (
                <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
                  {Object.entries({ program: p.program, provider: p.provider, model: p.model ?? '-', mode: p.mode, 'max repairs': p.max_repairs, 'review gates': (p.gates as string[]).join(', ') || 'none' }).map(([k, v]) => (
                    <div key={k} className="contents"><dt className="text-slate-500">{k}</dt><dd className="font-mono text-slate-300">{String(v)}</dd></div>
                  ))}
                </dl>
              )}
              {!compiled && <Spinner />}
              <p className="text-[11px] text-slate-500">Running the board starts a real migration with exactly these settings, checked against your role.</p>
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}

export default function Orchestrator() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold text-fg">Orchestrator</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-400">
          Wire the AI agents into a pipeline, like a workflow builder. The board is saved per project and compiles to a real run: the generator, the build and verify steps,
          the repair loop and any human review gates. Agents your role cannot use are locked.
        </p>
      </div>
      <ReactFlowProvider><Board /></ReactFlowProvider>
    </div>
  )
}
