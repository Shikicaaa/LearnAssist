import { useState } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import { describeError } from '../../lib/api/client'
import { SidebarIcon } from '../../components/ui'
import { useAuth } from '../auth/AuthContext'
import { Composer } from '../chat/Composer'
import { CornerCorgi } from '../room/CornerCorgi'
import '../chat/chat.css'
import { useSessions } from '../sessions/SessionsContext'
import type { ShellContext } from './AppShell'

function greeting() {
  const h = new Date().getHours()
  if (h < 5) return 'Burning the midnight oil'
  if (h < 12) return 'Good morning'
  if (h < 18) return 'Good afternoon'
  return 'Good evening'
}

/** /app with no notebook selected. Asking something here creates a notebook for it. */
export function WelcomePage() {
  const { user } = useAuth()
  const { create } = useSessions()
  const { openSidebar } = useOutletContext<ShellContext>()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const name = user?.email.split('@')[0]

  async function onSend(question: string) {
    setError(null)
    try {
      const title = question.length > 48 ? `${question.slice(0, 47)}…` : question
      const session = await create(title)
      navigate(`/app/${session.id}`, { state: { question } })
    } catch (err) {
      setError(describeError(err))
    }
  }

  return (
    <div className="welcome">
      <button className="icon-btn welcome__burger" onClick={openSidebar} aria-label="Open notebooks">
        <SidebarIcon />
      </button>
      <h1>
        {greeting()}, <span>{name}</span>
      </h1>
      <div className="welcome__composer">
        <div className="chat__dock-main">
          <Composer onSend={onSend} placeholder="What are you studying today?" autoFocus />
        </div>
        <CornerCorgi />
      </div>
      {error && (
        <div className="alert" role="alert">
          {error}
        </div>
      )}
      <p className="welcome__hint">Or press NEW, then add your sources — answers only come from what you upload.</p>
    </div>
  )
}
