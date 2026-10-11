import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { SessionsProvider } from '../sessions/SessionsContext'
import { Sidebar } from '../sessions/Sidebar'
import './shell.css'

export interface ShellContext {
  openSidebar: () => void
}

/** Left: notebook list. Right: whatever route is active (welcome screen or a notebook). */
export function AppShell() {
  const [open, setOpen] = useState(false)
  const context: ShellContext = { openSidebar: () => setOpen(true) }

  return (
    <SessionsProvider>
      <div className={`shell ${open ? 'shell--side-open' : ''}`}>
        <aside className="shell__side">
          <Sidebar onNavigate={() => setOpen(false)} />
        </aside>
        {open && <div className="shell__scrim" onClick={() => setOpen(false)} />}
        <div className="shell__main">
          <Outlet context={context} />
        </div>
      </div>
    </SessionsProvider>
  )
}
