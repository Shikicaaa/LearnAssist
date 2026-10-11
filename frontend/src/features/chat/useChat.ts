import { useCallback, useEffect, useRef, useState } from 'react'
import { describeError } from '../../lib/api/client'
import { chatApi } from '../../lib/api/endpoints'
import type { Citation, Message } from '../../lib/api/types'

export interface ChatMessage extends Message {
  pending?: boolean // the answer is still streaming in
  error?: string // the answer failed; show this instead of (or under) the text
  stopped?: boolean // the user stopped it
}

let tempId = 0
const draft = (role: Message['role'], content: string): ChatMessage => ({
  id: `tmp-${++tempId}`,
  role,
  content,
  cached: false,
  llm_provider: null,
  llm_model: null,
  tokens_in: 0,
  tokens_out: 0,
  created_at: new Date().toISOString(),
  citations: [],
})

export function useChat(sid: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [streaming, setStreaming] = useState(false)
  const [total, setTotal] = useState(0)
  const abort = useRef<AbortController | null>(null)

  // Load the history when the session changes; cancel whatever was streaming for the old one.
  useEffect(() => {
    abort.current?.abort()
    setMessages([])
    setStreaming(false)
    setLoading(true)
    let cancelled = false
    chatApi
      .history(sid)
      .then((page) => {
        if (cancelled) return
        setMessages([...page.items].reverse()) // the API sends the newest first
        setTotal(page.total)
      })
      .catch(() => {})
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
      abort.current?.abort()
    }
  }, [sid])

  const loadOlder = useCallback(async () => {
    const stored = messages.filter((m) => !m.id.startsWith('tmp-')).length
    const page = await chatApi.history(sid, stored)
    setMessages((list) => [...[...page.items].reverse(), ...list])
    setTotal(page.total)
  }, [sid, messages])

  const send = useCallback(
    async (question: string, useCache = true, allowGeneral = false) => {
      const answer = draft('assistant', '')
      answer.pending = true
      setMessages((list) => [...list, draft('user', question), answer])
      setStreaming(true)

      const controller = new AbortController()
      abort.current = controller
      const patch = (fn: (m: ChatMessage) => ChatMessage) =>
        setMessages((list) => list.map((m) => (m.id === answer.id ? fn(m) : m)))

      try {
        for await (const { event, data } of await chatApi.ask(sid, question, useCache, allowGeneral, controller.signal)) {
          if (controller.signal.aborted) return
          if (event === 'delta') {
            const { text } = data as { text: string }
            patch((m) => ({ ...m, content: m.content + text }))
          } else if (event === 'citations') {
            const { citations } = data as { citations: Citation[] }
            patch((m) => ({ ...m, citations }))
          } else if (event === 'done') {
            const { message } = data as { message: Message }
            patch(() => message) // swap the draft for the stored message (real id, token counts)
          } else if (event === 'error') {
            const { message } = data as { message: string }
            patch((m) => ({ ...m, pending: false, error: message }))
          }
        }
        patch((m) => (m.pending ? { ...m, pending: false } : m))
      } catch (err) {
        if (controller.signal.aborted) {
          patch((m) => ({ ...m, pending: false, stopped: true }))
        } else {
          patch((m) => ({ ...m, pending: false, error: describeError(err) }))
        }
      } finally {
        if (abort.current === controller) {
          abort.current = null
          setStreaming(false)
        }
      }
    },
    [sid],
  )

  const stop = useCallback(() => abort.current?.abort(), [])

  const clear = useCallback(async () => {
    await chatApi.clear(sid)
    setMessages([])
    setTotal(0)
  }, [sid])

  const hasMore = messages.filter((m) => !m.id.startsWith('tmp-')).length < total
  return { messages, loading, streaming, hasMore, send, stop, clear, loadOlder }
}
