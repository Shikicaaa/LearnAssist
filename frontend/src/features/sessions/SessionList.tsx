import { useState, type KeyboardEvent } from 'react'
import { NavLink, useNavigate, useParams } from 'react-router-dom'
import { ChatIcon, Menu, TrashIcon } from '../../components/ui'
import { useSessions } from './SessionsContext'
import type { Session } from '../../lib/api/types'

function SessionRow({ session, onNavigate }: { session: Session; onNavigate: () => void }) {
  const { rename, remove } = useSessions()
  const navigate = useNavigate()
  const active = useParams().sid === session.id
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(session.title)

  async function commit() {
    setEditing(false)
    const title = draft.trim()
    if (title && title !== session.title) await rename(session.id, title).catch(() => {})
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Enter') void commit()
    if (e.key === 'Escape') setEditing(false)
  }

  async function onDelete() {
    if (!window.confirm(`Delete “${session.title}” with all its sources and messages?`)) return
    await remove(session.id)
    if (active) navigate('/app')
  }

  return (
    <li className={`sessions__row ${active ? 'is-active' : ''}`}>
      {editing ? (
        <input
          className="input sessions__edit"
          autoFocus
          value={draft}
          maxLength={200}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={onKey}
          aria-label="Notebook name"
        />
      ) : (
        <NavLink to={`/app/${session.id}`} className="sessions__link" onClick={onNavigate} title={session.title}>
          <ChatIcon size={16} />
          <span>{session.title}</span>
        </NavLink>
      )}
      {!editing && (
        <Menu
          label={`Actions for ${session.title}`}
          items={[
            {
              label: 'Rename',
              onSelect: () => {
                setDraft(session.title)
                setEditing(true)
              },
            },
            { label: 'Delete', icon: <TrashIcon size={16} />, danger: true, onSelect: onDelete },
          ]}
        />
      )}
    </li>
  )
}

export function SessionList({ filter, onNavigate }: { filter: string; onNavigate: () => void }) {
  const { sessions, loading } = useSessions()
  const shown = sessions.filter((s) => s.title.toLowerCase().includes(filter.trim().toLowerCase()))

  if (loading) return <p className="sessions__hint">Loading…</p>
  if (sessions.length === 0) return <p className="sessions__hint">No notebooks yet. Hit NEW to start one.</p>
  if (shown.length === 0) return <p className="sessions__hint">Nothing matches “{filter}”.</p>

  return (
    <ul className="sessions">
      {shown.map((s) => (
        <SessionRow key={s.id} session={s} onNavigate={onNavigate} />
      ))}
    </ul>
  )
}
