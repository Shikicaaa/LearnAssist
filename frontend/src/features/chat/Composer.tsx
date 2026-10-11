import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { BoltIcon, SendIcon, StopIcon } from '../../components/ui'
import { signalTyping } from '../room/typing'

const GENERAL_KEY = 'allowGeneral'

/** The "general knowledge" choice outlives the page; storage can be blocked, so never throw. */
export function loadAllowGeneral(): boolean {
  try {
    return localStorage.getItem(GENERAL_KEY) === '1'
  } catch {
    return false
  }
}

function saveAllowGeneral(value: boolean) {
  try {
    localStorage.setItem(GENERAL_KEY, value ? '1' : '0')
  } catch {
    /* the choice just won't be remembered */
  }
}

interface Props {
  onSend: (question: string, useCache: boolean, allowGeneral: boolean) => void
  onStop?: () => void
  streaming?: boolean
  disabled?: boolean
  placeholder?: string
  /** Shown in the bottom row, e.g. "3 sources". */
  hint?: string
  autoFocus?: boolean
}

export function Composer({ onSend, onStop, streaming, disabled, placeholder, hint, autoFocus }: Props) {
  const [text, setText] = useState('')
  const [useCache, setUseCache] = useState(true)
  const [allowGeneral, setAllowGeneral] = useState(loadAllowGeneral)
  const ref = useRef<HTMLTextAreaElement>(null)

  // grow with the content up to a limit
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [text])

  function submit() {
    const question = text.trim()
    if (!question || streaming || disabled) return
    onSend(question, useCache, allowGeneral)
    setText('')
  }

  function onKeyDown(e: KeyboardEvent) {
    // the corgi types along; bare modifier keys and shortcuts are not typing
    if (!e.ctrlKey && !e.metaKey && (e.key.length === 1 || e.key === 'Backspace' || e.key === 'Enter')) signalTyping()
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="composer">
      <div className="composer__box">
        <textarea
          ref={ref}
          rows={1}
          value={text}
          autoFocus={autoFocus}
          maxLength={2000}
          disabled={disabled}
          placeholder={placeholder ?? 'Ask a question about your sources…'}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          aria-label="Your question"
        />
        <div className="composer__row">
          <button
            type="button"
            className={`composer__toggle ${useCache ? '' : 'is-on'}`}
            onClick={() => setUseCache((v) => !v)}
            aria-pressed={!useCache}
            title="Skip remembered answers and generate a new one"
          >
            <BoltIcon size={14} /> Fresh answer
          </button>
          <button
            type="button"
            className={`composer__toggle ${allowGeneral ? 'is-on' : ''}`}
            onClick={() =>
              setAllowGeneral((v) => {
                saveAllowGeneral(!v)
                return !v
              })
            }
            aria-pressed={allowGeneral}
            title="When your sources don't cover the question, let the AI answer from general knowledge (clearly labelled)"
          >
            General knowledge
          </button>
          <span className="composer__hint mono">{hint}</span>
          {streaming ? (
            <button className="composer__send" onClick={onStop} aria-label="Stop generating">
              <StopIcon />
            </button>
          ) : (
            <button className="composer__send" onClick={submit} disabled={!text.trim() || disabled} aria-label="Send">
              <SendIcon />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
