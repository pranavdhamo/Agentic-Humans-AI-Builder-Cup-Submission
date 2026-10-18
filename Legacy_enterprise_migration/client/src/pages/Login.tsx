import { useState, type FormEvent } from 'react'
import { useAuth } from '../lib/AuthContext'
import { ThemeToggle } from '../lib/theme'
import { ErrorNote, Spinner } from '../components/ui'

const DEMO = [
  ['admin@studio.local', 'Project Admin'],
  ['architect@studio.local', 'Lead Architect'],
  ['senior@studio.local', 'Senior Developer'],
  ['junior@studio.local', 'Junior Developer'],
  ['intern@studio.local', 'Intern'],
]

export default function Login() {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email, password)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="relative flex min-h-full items-center justify-center p-6">
      <div className="absolute right-5 top-5"><ThemeToggle /></div>
      <div className="grid w-full max-w-4xl gap-8 md:grid-cols-2">
        <div className="flex flex-col justify-center">
          <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-brand to-blue-700 text-lg font-bold text-white">MS</div>
          <h1 className="text-3xl font-semibold text-fg">Migration Studio</h1>
          <p className="mt-3 text-sm leading-relaxed text-slate-400">
            Gemini ports mainframe COBOL to Java. Every output record is checked against what the real COBOL produced.
            Sign in to work in your project; the AI agents you can use, the models and your budgets depend on your role.
          </p>
          <ul className="mt-5 space-y-2 text-sm text-slate-400">
            <li>{'•'} Interns verify and explore; juniors generate with the basic model</li>
            <li>{'•'} Seniors repair, approve human gates and edit the orchestration board</li>
            <li>{'•'} Lead architects get the advanced models; admins manage IAM and keys</li>
          </ul>
        </div>

        <form onSubmit={submit} className="card space-y-4 p-6" aria-label="Sign in">
          <h2 className="text-lg font-semibold text-fg">Sign in</h2>
          <div>
            <label className="label" htmlFor="email">Email</label>
            <input id="email" className="input" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div>
            <label className="label" htmlFor="pw">Password</label>
            <input id="pw" className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
          <ErrorNote message={error} />
          <button className="btn btn-primary w-full" disabled={busy}>{busy ? <Spinner /> : 'Sign in'}</button>

          <div className="border-t border-ink-600/60 pt-4">
            <div className="label">Demo accounts (password <span className="font-mono normal-case">studio123</span>, admin: <span className="font-mono normal-case">admin123</span>)</div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {DEMO.map(([em, label]) => (
                <button key={em} type="button" className="chip" onClick={() => { setEmail(em); setPassword(em.startsWith('admin') ? 'admin123' : 'studio123') }}>{label}</button>
              ))}
            </div>
            <p className="mt-2 text-[11px] text-slate-500">Seeded for local demos. Change them under Admin before sharing the studio.</p>
          </div>
        </form>
      </div>
    </div>
  )
}
