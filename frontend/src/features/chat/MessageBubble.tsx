import type { Citation } from '../../lib/api/types'
import { BoltIcon } from '../../components/ui'
import { useAnimal } from './animal'
import { MarkdownMessage } from './MarkdownMessage'
import { PixelAnimal } from './PixelAnimal'
import type { ChatMessage } from './useChat'

function pages(c: Citation) {
  if (c.page_start == null) return null
  return c.page_end && c.page_end !== c.page_start ? `pp. ${c.page_start}–${c.page_end}` : `p. ${c.page_start}`
}

export function MessageBubble({ message, onCitation }: { message: ChatMessage; onCitation: (c: Citation) => void }) {
  const animal = useAnimal()
  if (message.role === 'user') {
    return (
      <div className="msg msg--user">
        <div className="msg__bubble">{message.content}</div>
      </div>
    )
  }

  return (
    <div className="msg msg--assistant">
      <div className="msg__avatar" aria-hidden="true">
        <PixelAnimal animal={animal} busy={message.pending} />
      </div>
      <div className="msg__main">
        <AssistantContent message={message} onCitation={onCitation} />
      </div>
    </div>
  )
}

/** The answer itself (text, citations, notes). Used in the message list and in the corgi's bubble. */
export function AssistantContent({ message, onCitation }: { message: ChatMessage; onCitation: (c: Citation) => void }) {
  const waiting = message.pending && !message.content
  return (
    <>
      {waiting ? (
        <div className="typing" aria-label="Thinking">
          <span /> <span /> <span />
        </div>
      ) : (
        <MarkdownMessage content={message.content} citations={message.citations} onCitation={onCitation} />
      )}
      {message.pending && message.content && <span className="caret" />}
      {message.stopped && <div className="msg__note mono">stopped</div>}
      {message.error && (
        <div className="alert" role="alert">
          {message.error}
        </div>
      )}
      {message.citations.length > 0 && (
        <ul className="refs">
          {message.citations.map((c) => (
            <li key={c.rank}>
              <button className="ref" onClick={() => onCitation(c)}>
                <span className="cite">{c.rank}</span>
                <span className="ref__title">{c.source_title}</span>
                {pages(c) && <span className="ref__pages mono">{pages(c)}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
      {message.cached && (
        <div className="msg__note mono">
          <BoltIcon size={12} /> from memory
        </div>
      )}
    </>
  )
}
