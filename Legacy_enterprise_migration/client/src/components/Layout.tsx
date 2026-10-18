import { NavLink, Outlet } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/AuthContext'
import { duration } from '../lib/format'
import { useJob } from '../lib/JobContext'
import { ThemeToggle } from '../lib/theme'
import { useAsync } from '../lib/useAsync'
import { Badge, Spinner, statusTone } from './ui'

const ICON: Record<string, string> = {
  dash: 'M3 12l9-9 9 9M5 10v10h14V10',
  studio: 'M12 3l2.5 5.5L20 9l-4 4 1 6-5-3-5 3 1-6-4-4 5.5-.5z',
  board: 'M4 6h6v4H4zM14 14h6v4h-6zM7 10v4h7M14 8h6',
  verify: 'M5 12l4 4 10-10',
  runs: 'M4 6h16M4 12h16M4 18h10',
  explore: 'M8 6l-5 6 5 6M16 6l5 6-5 6',
  admin: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z',
}
const NAV = [
  { to: '/', label: 'Dashboard', icon: 'dash', end: true },
  { to: '/studio', label: 'Migration Studio', icon: 'studio' },
  { to: '/orchestrator', label: 'Orchestrator', icon: 'board' },
  { to: '/verifier', label: 'Verifier', icon: 'verify' },
  { to: '/runs', label: 'Run History', icon: 'runs' },
  { to: '/explorer', label: 'Oracle Explorer', icon: 'explore' },
  { to: '/admin', label: 'Admin and IAM', icon: 'admin', admin: true },
]

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={d} />
    </svg>
  )
}

function JobPill() {
  const { job, busy, cancel, gate } = useJob()
  if (!job) return <Badge>no jobs yet</Badge>
  const elapsed = (job.finished ?? Date.now() / 1000) - (job.started ?? job.created)
  return (
    <div className="flex items-center gap-2">
      {busy && <Spinner />}
      {gate && <Badge tone="warn">{'✋'} awaiting review</Badge>}
      <Badge tone={statusTone(job.status)}>{job.kind} - {job.status}</Badge>
      <span className="hidden text-xs text-slate-500 lg:inline">{duration(elapsed)}</span>
      {busy && <button className="btn btn-danger px-2 py-1 text-xs" onClick={cancel}>Cancel</button>}
    </div>
  )
}

export function RoleBadge({ role, label }: { role: string; label?: string }) {
  const tone = role === 'project_admin' ? 'bad' : role === 'lead_architect' ? 'brand' : role === 'senior_dev' ? 'ok' : role === 'junior_dev' ? 'warn' : 'mute'
  return <Badge tone={tone}>{label ?? role}</Badge>
}

export default function Layout() {
  const health = useAsync(api.health, [])
  const { profile, project, setProjectId, logout } = useAuth()
  const nav = NAV.filter((n) => !n.admin || profile?.user.role === 'project_admin')
  return (
    <div className="flex h-full">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-ink-600/60 bg-ink-900/70 md:flex">
        <div className="flex items-center gap-3 border-b border-ink-600/60 px-4 py-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-brand to-blue-700 text-sm font-bold text-white">MS</div>
          <div>
            <div className="text-sm font-semibold text-fg">Migration Studio</div>
            <div className="text-[11px] text-slate-500">COBOL to Java, proven</div>
          </div>
        </div>
        <nav className="flex-1 space-y-1 overflow-y-auto p-3">
          {nav.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => `nav ${isActive ? 'nav-on' : ''}`}>
              <Icon d={ICON[n.icon]} />
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-ink-600/60 p-4 text-[11px] text-slate-500">
          <div className="flex items-center gap-2">
            <span className={`h-2 w-2 rounded-full ${health.data ? 'bg-ok' : health.error ? 'bg-bad' : 'bg-warn'}`} />
            {health.data ? `API v${health.data.version}` : health.error ? 'API offline' : 'connecting...'}
          </div>
          <div className="mt-1">Ground truth: the real COBOL, never a model.</div>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-ink-600/60 bg-ink-900/50 px-5 py-2.5 backdrop-blur">
          <div className="flex items-center gap-3">
            <nav className="flex gap-1 md:hidden">
              {nav.map((n) => (
                <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => `nav px-2 py-1 text-xs ${isActive ? 'nav-on' : ''}`}>{n.label.split(' ')[0]}</NavLink>
              ))}
            </nav>
            <label className="hidden items-center gap-2 text-xs text-slate-500 md:flex">
              Project
              <select className="input w-auto min-w-[200px] py-1.5" value={project?.id ?? ''} onChange={(e) => setProjectId(e.target.value)} aria-label="Active project">
                {(profile?.projects ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                {!profile?.projects.length && <option value="">no project assigned</option>}
              </select>
            </label>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <JobPill />
            <ThemeToggle />
            {profile && (
              <div className="flex items-center gap-2 border-l border-ink-600/60 pl-3">
                <div className="text-right leading-tight">
                  <div className="text-xs font-medium text-fg">{profile.user.name}</div>
                  <RoleBadge role={profile.user.role} label={profile.user.role_label} />
                </div>
                <button className="btn px-2.5 py-1.5 text-xs" onClick={logout}>Sign out</button>
              </div>
            )}
          </div>
        </header>
        <main className="flex-1 overflow-y-auto p-5 lg:p-7">
          {health.error && (
            <div className="mb-5 rounded-lg border border-warn/30 bg-warn/10 px-4 py-3 text-sm text-warn">
              Cannot reach the API. Start it with <code className="font-mono">uvicorn app.main:app --port 8000</code> in <code className="font-mono">server/</code>.
            </div>
          )}
          {!project && (
            <div className="mb-5 rounded-lg border border-warn/30 bg-warn/10 px-4 py-3 text-sm text-warn">
              You are not assigned to any project yet. Ask a project admin to add you or your team.
            </div>
          )}
          <Outlet />
        </main>
      </div>
    </div>
  )
}
