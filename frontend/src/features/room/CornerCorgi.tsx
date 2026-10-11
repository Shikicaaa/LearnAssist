import { useEffect, useRef, useState } from 'react'
import { RoomCanvas } from './RoomCanvas'
import { onTyping, useRoomEnabled } from './typing'

interface Thought {
  id: number
  dx: number
  dy: number
}

/**
 * A corgi at a desk in the corner beside the chat bar. Whatever the student types, the corgi types
 * too, and little thought bubbles float from its laptop towards the chat bar.
 */
export function CornerCorgi() {
  const enabled = useRoomEnabled()
  const [thoughts, setThoughts] = useState<Thought[]>([])
  const next = useRef(0)
  const last = useRef(0)

  useEffect(() => {
    if (!enabled) return
    return onTyping(() => {
      const now = performance.now()
      if (now - last.current < 120) return
      last.current = now
      const id = ++next.current
      const thought = { id, dx: -(95 + Math.random() * 45), dy: -(18 + Math.random() * 46) }
      setThoughts((list) => [...list.slice(-7), thought])
      setTimeout(() => setThoughts((list) => list.filter((t) => t.id !== id)), 1300)
    })
  }, [enabled])

  if (!enabled) return null
  return (
    <div className="corner-corgi">
      <RoomCanvas view="corner" />
      {thoughts.map((t) => (
        <span key={t.id} className="thought" style={{ '--dx': `${t.dx}px`, '--dy': `${t.dy}px` } as React.CSSProperties} />
      ))}
    </div>
  )
}
