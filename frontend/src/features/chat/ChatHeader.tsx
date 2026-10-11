import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { sessionsApi } from '../../lib/api/endpoints'
import type { Session } from '../../lib/api/types'
import { BooksIcon, Menu, SidebarIcon, TrashIcon, BoltIcon, ChatIcon, MoonIcon } from '../../components/ui'
import { setRoomEnabled, useRoomEnabled } from '../room/typing'
import { setAnimal, useAnimal } from './animal'
import { useSessions } from '../sessions/SessionsContext'

interface Props {
  session: Session
  onOpenSidebar: () => void
  onOpenSources: () => void
  onClearChat: () => Promise<void>
}

export function ChatHeader({ session, onOpenSidebar, onOpenSources, onClearChat }: Props) {
  const { rename, remove, setCacheEnabled } = useSessions()
  const navigate = useNavigate()
  const roomEnabled = useRoomEnabled()
  const animal = useAnimal()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(session.title)

  async function commit() {
    setEditing(false)
    const title = draft.trim()
    if (title && title !== session.title) await rename(session.id, title).catch(() => {})
  }

  return (
    <header className="chat__head">
      <button className="icon-btn chat__burger" onClick={onOpenSidebar} aria-label="Open notebooks">
        <SidebarIcon />
      </button>

      {editing ? (
        <input
          className="input chat__title-input"
          autoFocus
          value={draft}
          maxLength={200}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void commit()
            if (e.key === 'Escape') setEditing(false)
          }}
        />
      ) : (
        <h1
          className="chat__title"
          title="Click to rename"
          onClick={() => {
            setDraft(session.title)
            setEditing(true)
          }}
        >
          {session.title}
        </h1>
      )}

      <div className="chat__tools">
        <button className="icon-btn chat__sources-btn" onClick={onOpenSources} aria-label="Open sources">
          <BooksIcon />
        </button>
        <Menu
          label="Notebook settings"
          items={[
            {
              label: session.cache_enabled ? 'Turn answer memory off' : 'Turn answer memory on',
              icon: <BoltIcon size={16} />,
              onSelect: () => void setCacheEnabled(session.id, !session.cache_enabled),
            },
            {
              label: 'Forget remembered answers',
              icon: <BoltIcon size={16} />,
              onSelect: () => void sessionsApi.clearCache(session.id),
            },
            {
              label: roomEnabled ? 'Hide the typing corgi' : 'Show the typing corgi',
              icon: <MoonIcon size={16} />,
              onSelect: () => setRoomEnabled(!roomEnabled),
            },
            {
              label: animal === 'capybara' ? 'Answer as a corgi' : 'Answer as a capybara',
              icon: <ChatIcon size={16} />,
              onSelect: () => setAnimal(animal === 'capybara' ? 'corgi' : 'capybara'),
            },
            {
              label: 'Clear conversation',
              icon: <ChatIcon size={16} />,
              onSelect: () => window.confirm('Clear all messages in this notebook?') && void onClearChat(),
            },
            {
              label: 'Delete notebook',
              icon: <TrashIcon size={16} />,
              danger: true,
              onSelect: async () => {
                if (!window.confirm(`Delete “${session.title}” with all its sources and messages?`)) return
                await remove(session.id)
                navigate('/app')
              },
            },
          ]}
        />
      </div>
    </header>
  )
}
