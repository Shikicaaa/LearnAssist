import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { DEFAULT_SESSION_TITLE } from '../../lib/brand'
import type { Citation, Session } from '../../lib/api/types'
import { Button } from '../../components/ui'
import { useSessions } from '../sessions/SessionsContext'
import { ChatHeader } from './ChatHeader'
import { CitationModal } from './CitationModal'
import { Composer, loadAllowGeneral } from './Composer'
import { CornerCorgi } from '../room/CornerCorgi'
import { MessageBubble } from './MessageBubble'
import { useChat } from './useChat'
import './chat.css'

interface Props {
  session: Session
  readyCount: number
  sourceCount: number
  onOpenSidebar: () => void
  onOpenSources: () => void
}

export function ChatView({ session, readyCount, sourceCount, onOpenSidebar, onOpenSources }: Props) {
  const { messages, loading, streaming, hasMore, send, stop, clear, loadOlder } = useChat(session.id)
  const { rename } = useSessions()
  const [citation, setCitation] = useState<Citation | null>(null)
  const scroller = useRef<HTMLDivElement>(null)
  const stick = useRef(true) // follow the stream only while the user is at the bottom
  const location = useLocation()
  const navigate = useNavigate()
  const handedOver = useRef(false)

  const ask = (question: string, useCache: boolean, allowGeneral: boolean) => {
    // The first question names the notebook, like in chat apps.
    if (session.title === DEFAULT_SESSION_TITLE && messages.length === 0) {
      const title = question.length > 48 ? `${question.slice(0, 47)}…` : question
      void rename(session.id, title).catch(() => {})
    }
    stick.current = true
    void send(question, useCache, allowGeneral)
  }

  // A question typed on the welcome screen arrives here through the router state.
  useEffect(() => {
    const initial = (location.state as { question?: string } | null)?.question
    if (!initial || loading || handedOver.current) return
    handedOver.current = true
    navigate(location.pathname, { replace: true, state: null })
    ask(initial, true, loadAllowGeneral())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading])

  useEffect(() => {
    const el = scroller.current
    if (el && stick.current) el.scrollTop = el.scrollHeight
  }, [messages])

  const empty = !loading && messages.length === 0
  const hint = sourceCount === 0 ? 'no sources yet' : `${readyCount}/${sourceCount} sources ready`

  const hello = (
    <div className="chat__hello">
      <h2>Ready when you are</h2>
      <p>
        {sourceCount === 0
          ? 'Start by adding a source on the right — a PDF, a Word file or some pasted text.'
          : 'Ask anything about your sources. Answers come with citations you can open.'}
      </p>
      {sourceCount === 0 && (
        <Button variant="ghost" className="chat__hello-btn" onClick={onOpenSources}>
          Add sources
        </Button>
      )}
    </div>
  )

  return (
    <section className={`chat ${empty ? 'chat--empty' : ''}`}>
      <ChatHeader session={session} onOpenSidebar={onOpenSidebar} onOpenSources={onOpenSources} onClearChat={clear} />

      <div
        className="chat__scroll"
        ref={scroller}
        onScroll={(e) => {
          const el = e.currentTarget
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
        }}
      >
        <div className="chat__col">
          {empty && hello}
          {hasMore && (
            <Button variant="ghost" size="sm" onClick={() => void loadOlder()} className="chat__older">
              Load earlier messages
            </Button>
          )}
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} onCitation={setCitation} />
          ))}
        </div>
      </div>

      <div className="chat__dock">
        <div className="chat__dock-row">
          <div className="chat__dock-main">
            <Composer onSend={ask} onStop={stop} streaming={streaming} disabled={loading} hint={hint} autoFocus />
            <p className="chat__disclaimer">Answers can contain mistakes — check the citations.</p>
          </div>
          <CornerCorgi />
        </div>
      </div>

      {citation && <CitationModal citation={citation} onClose={() => setCitation(null)} />}
    </section>
  )
}
