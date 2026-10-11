import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { describeError } from '../../lib/api/client'
import { BRAND } from '../../lib/brand'
import { Button, Field, Logo, ThemeToggle } from '../../components/ui'
import { useAuth } from './AuthContext'
import './auth.css'

type Mode = 'login' | 'register'

const COPY = {
  login: {
    title: 'Welcome back',
    sub: 'Pick up where your notes left off.',
    submit: 'Sign in',
    alt: ['New here?', 'Create an account', '/register'],
  },
  register: {
    title: 'Make yourself at home',
    sub: `Create your ${BRAND} account — it takes ten seconds.`,
    submit: 'Create account',
    alt: ['Already have an account?', 'Sign in', '/login'],
  },
} as const

export function AuthPage({ mode }: { mode: Mode }) {
  const { login, register } = useAuth()
  const navigate = useNavigate()
  const from = (useLocation().state as { from?: string } | null)?.from ?? '/app'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const copy = COPY[mode]

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await (mode === 'login' ? login : register)(email.trim(), password)
      navigate(from, { replace: true })
    } catch (err) {
      setError(describeError(err))
      setBusy(false)
    }
  }

  return (
    <div className="auth">
      <aside className="auth__side" aria-hidden="true">
        <blockquote>
          “Notes are just conversations with your future self.”
          <footer className="mono">— lofi study rule #1</footer>
        </blockquote>
      </aside>
      <main className="auth__main">
        <div className="auth__logo">
          <Logo />
          <ThemeToggle />
        </div>
        <form className="auth__card" onSubmit={onSubmit}>
          <h1>{copy.title}</h1>
          <p className="auth__sub">{copy.sub}</p>
          {error && (
            <div className="alert" role="alert">
              {error}
            </div>
          )}
          <Field
            label="Email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
          <Field
            label="Password"
            type="password"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            required
            minLength={mode === 'register' ? 8 : undefined}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={mode === 'register' ? 'At least 8 characters' : '••••••••'}
          />
          <Button type="submit" size="lg" block disabled={busy}>
            {busy ? <span className="spinner" /> : copy.submit}
          </Button>
          <p className="auth__alt">
            {copy.alt[0]} <Link to={copy.alt[2]}>{copy.alt[1]}</Link>
          </p>
        </form>
      </main>
    </div>
  )
}
