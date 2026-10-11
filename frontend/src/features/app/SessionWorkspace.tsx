import { useState } from 'react'
import { Navigate, useOutletContext, useParams } from 'react-router-dom'
import { ChatView } from '../chat/ChatView'
import { useSessions } from '../sessions/SessionsContext'
import { SourcesPanel } from '../sources/SourcesPanel'
import { useSources } from '../sources/useSources'
import type { ShellContext } from './AppShell'

/** One notebook: the chat in the middle, its sources on the right. */
export function SessionWorkspace() {
  const { sid = '' } = useParams()
  const { sessions, loading } = useSessions()
  const { openSidebar } = useOutletContext<ShellContext>()
  const { sources, loading: sourcesLoading, addLocal, removeLocal } = useSources(sid)
  const [sourcesOpen, setSourcesOpen] = useState(false)

  const session = sessions.find((s) => s.id === sid)
  if (loading) return null
  if (!session) return <Navigate to="/app" replace /> // deleted, or not ours (the API answers 404)

  return (
    <div className={`workspace ${sourcesOpen ? 'workspace--sources-open' : ''}`}>
      <div className="workspace__chat">
        <ChatView
          key={sid}
          session={session}
          sourceCount={sources.length}
          readyCount={sources.filter((s) => s.status === 'ready').length}
          onOpenSidebar={openSidebar}
          onOpenSources={() => setSourcesOpen(true)}
        />
      </div>
      {sourcesOpen && <div className="workspace__scrim" onClick={() => setSourcesOpen(false)} />}
      <aside className="workspace__sources">
        <SourcesPanel
          sid={sid}
          sources={sources}
          loading={sourcesLoading}
          onAdded={addLocal}
          onChanged={(s) => addLocal([s])}
          onRemoved={removeLocal}
          onClose={() => setSourcesOpen(false)}
        />
      </aside>
    </div>
  )
}
