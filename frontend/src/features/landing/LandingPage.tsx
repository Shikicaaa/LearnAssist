import { BRAND } from '../../lib/brand'
import { BooksIcon, BoltIcon, ButtonLink, ChatIcon, Logo, ThemeToggle } from '../../components/ui'
import { useAuth } from '../auth/AuthContext'
import { RoomCanvas } from '../room/RoomCanvas'
import { useRoomEnabled } from '../room/typing'
import { HeroScene } from './HeroScene'
import './landing.css'

const FEATURES = [
  {
    icon: <BooksIcon size={26} />,
    title: 'Bring your own sources',
    text: 'Drop in PDFs, Word files, Markdown or plain text. Each notebook keeps its own shelf, so topics never get mixed up.',
  },
  {
    icon: <ChatIcon size={26} />,
    title: 'Answers with receipts',
    text: 'Every answer points to the exact passage it came from — [1], [2], [3] — and one click shows the original text.',
  },
  {
    icon: <BoltIcon size={26} />,
    title: 'Quick and quiet',
    text: 'Answers stream in as they are written, and repeated questions come back instantly from the notebook’s memory.',
  },
]

export function LandingPage() {
  const { user } = useAuth()
  const roomEnabled = useRoomEnabled()
  const cta = user ? { to: '/app', label: 'Open your notebooks' } : { to: '/register', label: 'Start for free' }

  return (
    <div className="landing">
      <header className="landing__nav">
        <Logo />
        <nav>
          <ThemeToggle />
          {user ? (
            <ButtonLink to="/app" size="sm">
              Open app
            </ButtonLink>
          ) : (
            <>
              <ButtonLink to="/login" variant="ghost" size="sm">
                Sign in
              </ButtonLink>
              <ButtonLink to="/register" size="sm">
                Sign up
              </ButtonLink>
            </>
          )}
        </nav>
      </header>

      <section className="hero">
        <div className="hero__copy">
          <p className="hero__eyebrow mono">♪ study mode: on</p>
          <h1>
            Your sources, <em>finally</em> talking back.
          </h1>
          <p className="hero__lead">
            {BRAND} is a calm place to study. Upload your material, ask questions in plain language, and get answers
            that cite the page they came from.
          </p>
          <div className="hero__cta">
            <ButtonLink to={cta.to} size="lg">
              {cta.label}
            </ButtonLink>
            {!user && (
              <ButtonLink to="/login" variant="ghost" size="lg">
                I have an account
              </ButtonLink>
            )}
          </div>
        </div>
        <div className="hero__art">
          {roomEnabled ? (
            <div className="hero-room">
              <RoomCanvas view="room" />
            </div>
          ) : (
            <HeroScene />
          )}
          <div className="hero__bubble hero__bubble--q">What did chapter 3 say about entropy?</div>
          <div className="hero__bubble hero__bubble--a">
            Entropy measures disorder in a system <span className="chip">1</span> and never decreases in an isolated one{' '}
            <span className="chip">2</span>.
          </div>
        </div>
      </section>

      <section className="section">
        <h2 className="section__title">Everything a good study session needs</h2>
        <div className="features">
          {FEATURES.map((f) => (
            <article key={f.title} className="card">
              <div className="card__icon">{f.icon}</div>
              <h3>{f.title}</h3>
              <p>{f.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="final">
        <h2>Put the kettle on. Open a notebook.</h2>
        <ButtonLink to={cta.to} size="lg">
          {cta.label}
        </ButtonLink>
      </section>

      <footer className="landing__foot mono">
        © {new Date().getFullYear()} {BRAND} · built for slow, focused learning
      </footer>
    </div>
  )
}
