import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { describeError } from '../../lib/api/client'
import { DEFAULT_SESSION_TITLE } from '../../lib/brand'
import { Logo, LogoutIcon, PlusIcon, SearchIcon, ThemeToggle } from '../../components/ui'
import { useAuth } from '../auth/AuthContext'
import { SessionList } from './SessionList'
import { useSessions } from './SessionsContext'
import './sidebar.css'

export function Sidebar({ onNavigate }: { onNavigate: () => void }) {
  const { user, logout } = useAuth()
  const { create } = useSessions()
  const navigate = useNavigate()
  const [filter, setFilter] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function onNew() {
    setError(null)
    try {
      const session = await create(DEFAULT_SESSION_TITLE)
      navigate(`/app/${session.id}`)
      onNavigate()
    } catch (err) {
      setError(describeError(err))
    }
  }

  return (
    <div className="sidebar">
      <div className="sidebar__top">
        <Logo to="/app" />
      </div>

      <button className="sidebar__new" onClick={onNew}>
        <PlusIcon /> NEW
      </button>
      {error && (
        <div className="alert sidebar__error" role="alert">
          {error}
        </div>
      )}

      <label className="sidebar__search">
        <SearchIcon size={16} />
        <input
          placeholder="Search notebooks"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          aria-label="Search notebooks"
        />
      </label>

      <div className="sidebar__label mono">Notebooks</div>
      <div className="sidebar__scroll">
        <SessionList filter={filter} onNavigate={onNavigate} />
      </div>

      <div className="sidebar__user">
        <span className="sidebar__avatar">{user?.email[0]?.toUpperCase()}</span>
        <span className="sidebar__email" title={user?.email}>
          {user?.email}
        </span>
        <ThemeToggle />
        <button className="icon-btn" onClick={() => void logout()} aria-label="Sign out" title="Sign out">
          <LogoutIcon />
        </button>
      </div>
    </div>
  )
}
