import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './AuthContext'

function Splash() {
  return (
    <div style={{ height: '100%', display: 'grid', placeItems: 'center', color: 'var(--text-dim)' }}>
      <span className="spinner" />
    </div>
  )
}

/** Wraps the app routes: signed-out visitors go to /login and come back afterwards. */
export function RequireAuth() {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <Splash />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <Outlet />
}

/** Wraps login/register: a signed-in user has no business there. */
export function GuestOnly() {
  const { user, loading } = useAuth()
  if (loading) return <Splash />
  if (user) return <Navigate to="/app" replace />
  return <Outlet />
}
