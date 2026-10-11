import { useEffect, useState } from 'react'
import { MoonIcon, SunIcon } from './Icons'
import './ui.css'

type Theme = 'light' | 'dark'

/** The theme index.html already put on <html> before the first paint. */
function current(): Theme {
  return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark'
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(current)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.querySelector('meta[name="theme-color"]')?.setAttribute(
      'content',
      theme === 'light' ? '#f5e8d3' : '#030c14',
    )
    try {
      localStorage.setItem('theme', theme)
    } catch {
      /* private mode: the choice just won't be remembered */
    }
  }, [theme])

  const next = theme === 'light' ? 'dark' : 'light'
  return (
    <button
      type="button"
      className="icon-btn"
      onClick={() => setTheme(next)}
      aria-label={`Switch to ${next} mode`}
      title={`Switch to ${next} mode`}
    >
      {theme === 'light' ? <MoonIcon /> : <SunIcon />}
    </button>
  )
}
