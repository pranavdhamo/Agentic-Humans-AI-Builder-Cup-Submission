import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, setUnauthorizedHandler, tokenStore } from './api'
import type { Profile, Project } from './types'

interface AuthState {
  profile: Profile | null
  loading: boolean
  project: Project | null
  setProjectId: (id: string) => void
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  refresh: () => Promise<void>
  can: (flag: 'can_approve_gates' | 'can_edit_board' | 'can_run_verifier' | 'can_run_mutation' | 'can_run_build') => boolean
  hasAgent: (id: string) => boolean
}

const Ctx = createContext<AuthState | null>(null)
const PROJECT_KEY = 'studio-project'

const readProject = () => { try { return localStorage.getItem(PROJECT_KEY) } catch { return null } }

export function AuthProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [loading, setLoading] = useState(!!tokenStore.get())
  const [projectId, setPid] = useState<string | null>(readProject())

  const logout = useCallback(() => {
    tokenStore.clear()
    setProfile(null)
  }, [])

  useEffect(() => setUnauthorizedHandler(logout), [logout])

  const refresh = useCallback(async () => {
    setProfile(await api.me())
  }, [])

  useEffect(() => {
    if (!tokenStore.get()) return
    api.me().then(setProfile).catch(() => tokenStore.clear()).finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const r = await api.login(email, password)
    tokenStore.set(r.token)
    const { token: _token, ...rest } = r
    void _token
    setProfile(rest)
  }, [])

  const setProjectId = useCallback((id: string) => {
    setPid(id)
    try { localStorage.setItem(PROJECT_KEY, id) } catch { /* private mode */ }
  }, [])

  const value = useMemo<AuthState>(() => {
    const projects = profile?.projects ?? []
    const project = projects.find((p) => p.id === projectId) ?? projects[0] ?? null
    return {
      profile, loading, project, setProjectId, login, logout, refresh,
      can: (flag) => !!profile?.policy[flag],
      hasAgent: (id) => !!profile?.policy.agents.includes(id),
    }
  }, [profile, loading, projectId, setProjectId, login, logout, refresh])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth(): AuthState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAuth outside AuthProvider')
  return v
}
