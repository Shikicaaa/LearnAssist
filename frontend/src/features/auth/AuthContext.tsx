import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { setSessionExpiredHandler, tokens } from '../../lib/api/client'
import { authApi } from '../../lib/api/endpoints'
import type { User } from '../../lib/api/types'

interface AuthState {
  user: User | null
  /** True while we check a stored token on page load; routes wait for it. */
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(() => tokens.access !== null)

  useEffect(() => {
    setSessionExpiredHandler(() => setUser(null))
    if (!tokens.access) return
    authApi
      .me()
      .then(setUser)
      .catch(() => tokens.clear())
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    tokens.set(await authApi.login(email, password))
    setUser(await authApi.me())
  }, [])

  const register = useCallback(
    async (email: string, password: string) => {
      await authApi.register(email, password)
      await login(email, password) // the API returns no tokens on register, so sign in right away
    },
    [login],
  )

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } catch {
      /* the refresh token may already be invalid; we leave either way */
    }
    tokens.clear()
    setUser(null)
  }, [])

  const value = useMemo(() => ({ user, loading, login, register, logout }), [user, loading, login, register, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
