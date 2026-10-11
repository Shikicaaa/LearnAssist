import { Link } from 'react-router-dom'
import { BRAND } from '../../lib/brand'
import './ui.css'

export function Logo({ to = '/' }: { to?: string }) {
  return (
    <Link to={to} className="logo">
      <svg className="logo__mark" viewBox="0 0 32 32" aria-hidden="true">
        <rect width="32" height="32" rx="9" fill="var(--c-deep-teal)" />
        <path d="M9 8h10a4 4 0 0 1 4 4v12H13a4 4 0 0 1-4-4z" fill="var(--c-cream)" />
        <circle cx="21" cy="9" r="4" fill="var(--c-pink)" />
      </svg>
      {BRAND}
    </Link>
  )
}
