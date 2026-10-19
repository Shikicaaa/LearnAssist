import { useEffect, type ReactNode } from 'react'
import { CloseIcon } from './Icons'
import './ui.css'

interface ModalProps {
  title: string
  onClose: () => void
  children: ReactNode
  /** `lg` for content that needs room, such as the quiz. */
  size?: 'md' | 'lg'
}

export function Modal({ title, onClose, children, size = 'md' }: ModalProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${size === 'lg' ? 'modal--lg' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal__head">
          <h2 className="modal__title">{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <CloseIcon />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
