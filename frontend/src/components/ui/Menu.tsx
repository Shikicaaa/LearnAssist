import { useEffect, useRef, useState, type ReactNode } from 'react'
import { DotsIcon } from './Icons'
import './ui.css'

export interface MenuItem {
  label: string
  icon?: ReactNode
  danger?: boolean
  onSelect: () => void
}

export function Menu({ items, label = 'More actions' }: { items: MenuItem[]; label?: string }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false)
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', esc)
    }
  }, [open])

  return (
    <div className="menu" ref={ref}>
      <button className="icon-btn" aria-label={label} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <DotsIcon />
      </button>
      {open && (
        <div className="menu__list" role="menu">
          {items.map((item) => (
            <button
              key={item.label}
              role="menuitem"
              className={`menu__item ${item.danger ? 'menu__item--danger' : ''}`}
              onClick={() => {
                setOpen(false)
                item.onSelect()
              }}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
