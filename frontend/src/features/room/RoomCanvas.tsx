import { useEffect, useRef } from 'react'
import type { Room } from './scene'
import './room.css'

interface Props {
  view: 'room' | 'corner'
  className?: string
}

const themeNow = () => (document.documentElement.dataset.theme === 'light' ? 'light' : 'dark')

/**
 * The 3D scene, filling its parent. three.js is loaded on demand, so a student who switched the
 * corgi off never downloads it, and a browser without WebGL just shows nothing.
 */
export function RoomCanvas({ view, className = '' }: Props) {
  const host = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = host.current
    if (!el) return
    let room: Room | undefined
    let cancelled = false

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    import('./scene')
      .then(({ createRoom }) => {
        if (cancelled) return
        try {
          room = createRoom(el, { view, reducedMotion: reduced, theme: themeNow() })
        } catch {
          /* no WebGL: the scene is decoration */
        }
      })
      .catch(() => {})

    const watcher = new MutationObserver(() => room?.setTheme(themeNow()))
    watcher.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => {
      cancelled = true
      watcher.disconnect()
      room?.dispose()
    }
  }, [view])

  return <div className={`room-canvas ${className}`} ref={host} aria-hidden="true" />
}
