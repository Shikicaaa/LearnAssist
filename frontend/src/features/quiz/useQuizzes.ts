import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../../lib/api/client'
import { quizApi } from '../../lib/api/endpoints'
import type { Artifact, QuizRequest } from '../../lib/api/types'

const POLL_MS = 2000

const byNewest = (a: Artifact, b: Artifact) => b.created_at.localeCompare(a.created_at)

function upsert(list: Artifact[], next: Artifact): Artifact[] {
  const exists = list.some((q) => q.id === next.id)
  return (exists ? list.map((q) => (q.id === next.id ? next : q)) : [...list, next]).sort(byNewest)
}

/**
 * A session's quizzes. Generating one takes a few seconds to a minute and happens in a worker, so
 * a quiz comes back `pending`; while any is pending we ask for it again every couple of seconds
 * until it is `ready` or `failed`. Asking for the same settings twice returns the stored quiz at
 * once (the backend caches by what was asked and by the material).
 */
export function useQuizzes(sid: string) {
  const [quizzes, setQuizzes] = useState<Artifact[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // No reset needed: QuizStudio is keyed by session, so a new session is a fresh hook.
    let cancelled = false
    quizApi
      .list(sid)
      .then((page) => !cancelled && setQuizzes(page.items))
      .catch(() => {}) // the panel simply shows no quizzes; creating one reports its own errors
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [sid])

  // Poll the pending ones. Keyed by their ids, so it restarts only when that set changes.
  const pendingKey = quizzes
    .filter((q) => q.status === 'pending')
    .map((q) => q.id)
    .join(',')

  useEffect(() => {
    if (!pendingKey) return
    let cancelled = false

    async function poll() {
      while (!cancelled) {
        await new Promise((r) => setTimeout(r, POLL_MS))
        for (const id of pendingKey.split(',')) {
          try {
            const fresh = await quizApi.get(id)
            if (!cancelled) setQuizzes((list) => upsert(list, fresh))
          } catch (err) {
            // Deleted elsewhere: stop waiting for it. Anything else (network) we retry.
            if (err instanceof ApiError && err.status === 404 && !cancelled) {
              setQuizzes((list) => list.filter((q) => q.id !== id))
            }
          }
        }
      }
    }
    void poll()
    return () => {
      cancelled = true
    }
  }, [pendingKey])

  /** Throws an ApiError (rate limit, quota, no material...) for the caller to show. */
  const generate = useCallback(
    async (body: QuizRequest) => {
      const quiz = await quizApi.create(sid, body)
      setQuizzes((list) => upsert(list, quiz))
      return quiz
    },
    [sid],
  )

  const remove = useCallback(async (id: string) => {
    await quizApi.remove(id)
    setQuizzes((list) => list.filter((q) => q.id !== id))
  }, [])

  return { quizzes, loading, generate, remove }
}
