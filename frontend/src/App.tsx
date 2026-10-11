import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './features/app/AppShell'
import { SessionWorkspace } from './features/app/SessionWorkspace'
import { WelcomePage } from './features/app/WelcomePage'
import { AuthPage } from './features/auth/AuthPage'
import { AuthProvider } from './features/auth/AuthContext'
import { GuestOnly, RequireAuth } from './features/auth/RouteGuards'
import { LandingPage } from './features/landing/LandingPage'

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route element={<GuestOnly />}>
            <Route path="/login" element={<AuthPage mode="login" />} />
            <Route path="/register" element={<AuthPage mode="register" />} />
          </Route>
          <Route element={<RequireAuth />}>
            <Route path="/app" element={<AppShell />}>
              <Route index element={<WelcomePage />} />
              <Route path=":sid" element={<SessionWorkspace />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
