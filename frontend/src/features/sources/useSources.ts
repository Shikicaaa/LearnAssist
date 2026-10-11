import { useCallback, useEffect, useState } from 'react'
import { sourcesApi } from '../../lib/api/endpoints'
import type { Source } from '../../lib/api/types'

const byCreated = (a: Source, b: Source) => a.created_at.localeCompare(b.created_at)

function upsert(list: Source[], next: Source): Source[] {
  if (next.status === 'deleted') return list.filter((s) => s.id !== next.id)
  const exists = list.some((s) => s.id === next.id)
  return (exists ? list.map((s) => (s.id === next.id ? next : s)) : [...list, next]).sort(byCreated)
}

/**
 * The live list of a session's sources. The backend sends a `snapshot` first and then one
 * `source` event per change (queued -> processing -> ready/failed), so no polling is needed.
 * If the connection drops we reconnect with a growing delay; the new snapshot repairs any gap.
 */
export function useSources(sid: string) {
  const [sources, setSources] = useState<Source[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setSources([])
    setLoading(true)
    const controller = new AbortController()

    async function run() {
      let attempt = 0
      while (!controller.signal.aborted) {
        try {
          for await (const { event, data } of await sourcesApi.events(sid, controller.signal)) {
            attempt = 0
            if (event === 'snapshot') {
              setSources((data as { sources: Source[] }).sources.sort(byCreated))
              setLoading(false)
            } else if (event === 'source') {
              setSources((list) => upsert(list, data as Source))
            }
          }
        } catch {
          if (controller.signal.aborted) return
        }
        // The stream ended or failed: wait (1s, 2s, 4s ... max 15s) and reconnect.
        await new Promise((r) => setTimeout(r, Math.min(15000, 1000 * 2 ** attempt++)))
      }
    }
    void run()
    return () => controller.abort()
  }, [sid])

  /** Shows sources right away after an upload; the stream then keeps them up to date. */
  const addLocal = useCallback((added: Source[]) => {
    setSources((list) => added.reduce(upsert, list))
  }, [])
  const removeLocal = useCallback((id: string) => {
    setSources((list) => list.filter((s) => s.id !== id))
  }, [])

  return { sources, loading, addLocal, removeLocal }
}
