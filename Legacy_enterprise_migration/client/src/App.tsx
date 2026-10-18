import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { Spinner } from './components/ui'
import { useAuth } from './lib/AuthContext'
import Admin from './pages/Admin'
import Dashboard from './pages/Dashboard'
import Explorer from './pages/Explorer'
import Login from './pages/Login'
import Orchestrator from './pages/Orchestrator'
import Runs from './pages/Runs'
import Studio from './pages/Studio'
import Verifier from './pages/Verifier'

export default function App() {
  const { profile, loading } = useAuth()
  if (loading) return <div className="flex h-full items-center justify-center"><Spinner className="h-6 w-6" /></div>
  if (!profile) return <Login />
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="studio" element={<Studio />} />
        <Route path="orchestrator" element={<Orchestrator />} />
        <Route path="verifier" element={<Verifier />} />
        <Route path="runs" element={<Runs />} />
        <Route path="runs/:source/:name" element={<Runs />} />
        <Route path="explorer" element={<Explorer />} />
        <Route path="admin" element={profile.user.role === 'project_admin' ? <Admin /> : <Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
