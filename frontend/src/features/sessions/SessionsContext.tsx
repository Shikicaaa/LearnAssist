import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { sessionsApi } from '../../lib/api/endpoints'
import type { Session } from '../../lib/api/types'

interface SessionsState {
  sessions: Session[]
  loading: boolean
  create: (title: string) => Promise<Session>
  rename: (sid: string, title: string) => Promise<void>
  setCacheEnabled: (sid: string, enabled: boolean) => Promise<void>
  remove: (sid: string) => Promise<void>
}

const SessionsContext = createContext<SessionsState | null>(null)

const byRecent = (a: Session, b: Session) => b.updated_at.localeCompare(a.updated_at)

/** Holds the sidebar list; the chat view reads the active session from here too. */
export function SessionsProvider({ children }: { children: ReactNode }) {
  const [sessions, setSessions] = useState<Session[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    sessionsApi
      .list()
      .then((page) => setSessions(page.items.sort(byRecent)))
      .finally(() => setLoading(false))
  }, [])

  const replace = useCallback((next: Session) => {
    setSessions((list) => list.map((s) => (s.id === next.id ? next : s)))
  }, [])

  const create = useCallback(async (title: string) => {
    const session = await sessionsApi.create(title)
    setSessions((list) => [session, ...list])
    return session
  }, [])

  const rename = useCallback(
    async (sid: string, title: string) => replace(await sessionsApi.update(sid, { title })),
    [replace],
  )

  const setCacheEnabled = useCallback(
    async (sid: string, enabled: boolean) => replace(await sessionsApi.update(sid, { cache_enabled: enabled })),
    [replace],
  )

  const remove = useCallback(async (sid: string) => {
    await sessionsApi.remove(sid)
    setSessions((list) => list.filter((s) => s.id !== sid))
  }, [])

  const value = useMemo(
    () => ({ sessions, loading, create, rename, setCacheEnabled, remove }),
    [sessions, loading, create, rename, setCacheEnabled, remove],
  )
  return <SessionsContext.Provider value={value}>{children}</SessionsContext.Provider>
}

export function useSessions() {
  const ctx = useContext(SessionsContext)
  if (!ctx) throw new Error('useSessions must be used inside <SessionsProvider>')
  return ctx
}
