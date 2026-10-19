import { useState, type FormEvent } from 'react'
import { describeError } from '../../lib/api/client'
import type { Artifact, Difficulty, QuestionType, QuizRequest, QuizScript, Source } from '../../lib/api/types'
import { Button, Modal } from '../../components/ui'

const COUNTS = [5, 10, 15, 20]
const DIFFICULTIES: { value: Difficulty; label: string; hint: string }[] = [
  { value: 'easy', label: 'Easy', hint: 'Facts and definitions straight from the text' },
  { value: 'medium', label: 'Medium', hint: 'Understanding how ideas relate' },
  { value: 'hard', label: 'Hard', hint: 'Applying and comparing across the material' },
]
const TYPES: { value: QuestionType; label: string }[] = [
  { value: 'mcq', label: 'Multiple choice' },
  { value: 'true_false', label: 'True / False' },
]
const SCRIPTS: { value: QuizScript; label: string }[] = [
  { value: 'latin', label: 'Latinica' },
  { value: 'cyrillic', label: 'Ћирилица' },
]
const PROMPT_MAX = 200 // the backend's limit for the topic

function Segmented<T extends string | number>({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: T
  options: { value: T; label: string }[]
  onChange: (value: T) => void
}) {
  return (
    <div className="field">
      <span className="field__label">{label}</span>
      <div className="seg" role="radiogroup" aria-label={label}>
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={o.value === value}
            className={o.value === value ? 'is-on' : ''}
            onClick={() => onChange(o.value)}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  )
}

interface Props {
  /** Only sources that are ready can be used. */
  sources: Source[]
  onClose: () => void
  onGenerate: (body: QuizRequest) => Promise<Artifact>
  onCreated: (quiz: Artifact) => void
}

export function QuizSetupModal({ sources, onClose, onGenerate, onCreated }: Props) {
  const [count, setCount] = useState(10)
  const [difficulty, setDifficulty] = useState<Difficulty>('medium')
  const [types, setTypes] = useState<QuestionType[]>(['mcq', 'true_false'])
  const [script, setScript] = useState<QuizScript>('latin')
  const [prompt, setPrompt] = useState('')
  const [allSources, setAllSources] = useState(true)
  const [chosen, setChosen] = useState<Set<string>>(new Set())
  const [fresh, setFresh] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const toggleType = (t: QuestionType) =>
    setTypes((list) => (list.includes(t) ? list.filter((x) => x !== t) : [...list, t]))
  const toggleSource = (id: string) =>
    setChosen((set) => {
      const next = new Set(set)
      if (!next.delete(id)) next.add(id)
      return next
    })

  const canSubmit = types.length > 0 && (allSources || chosen.size > 0) && !busy

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!canSubmit) return
    setBusy(true)
    setError(null)
    const body: QuizRequest = {
      num_questions: count,
      difficulty,
      types,
      script,
      ...(prompt.trim() && { topic: prompt.trim() }),
      ...(!allSources && { source_ids: [...chosen] }),
      ...(fresh && { regenerate: true }),
    }
    try {
      onCreated(await onGenerate(body))
    } catch (err) {
      setError(describeError(err))
      setBusy(false)
    }
  }

  return (
    <Modal title="Generate a quiz" onClose={onClose}>
      <form className="quizform" onSubmit={submit}>
        {error && (
          <div className="alert" role="alert">
            {error}
          </div>
        )}

        <Segmented
          label="Number of questions"
          value={count}
          options={COUNTS.map((n) => ({ value: n, label: String(n) }))}
          onChange={setCount}
        />

        <div>
          <Segmented label="Difficulty" value={difficulty} options={DIFFICULTIES} onChange={setDifficulty} />
          <p className="quizform__hint">{DIFFICULTIES.find((d) => d.value === difficulty)?.hint}</p>
        </div>

        <div className="field">
          <span className="field__label">Question types</span>
          <div className="quizform__checks">
            {TYPES.map((t) => (
              <label key={t.value} className="check">
                <input type="checkbox" checked={types.includes(t.value)} onChange={() => toggleType(t.value)} />
                {t.label}
              </label>
            ))}
          </div>
          {types.length === 0 && <p className="quizform__hint quizform__hint--warn">Pick at least one type.</p>}
        </div>

        <div className="field">
          <label className="field__label" htmlFor="quiz-prompt">
            Focus prompt (optional)
          </label>
          <textarea
            id="quiz-prompt"
            className="input"
            rows={3}
            maxLength={PROMPT_MAX}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder='e.g. "The Calvin cycle" or "causes of the battle"'
          />
          <p className="quizform__hint">
            Narrows the quiz to the part of your sources that matches. Leave it empty to cover everything.
            <span className="mono quizform__count">
              {prompt.length}/{PROMPT_MAX}
            </span>
          </p>
        </div>

        <div className="field">
          <span className="field__label">Sources</span>
          <label className="check">
            <input type="checkbox" checked={allSources} onChange={(e) => setAllSources(e.target.checked)} />
            Use all sources ({sources.length})
          </label>
          {!allSources && (
            <ul className="quizform__sources">
              {sources.map((s) => (
                <li key={s.id}>
                  <label className="check">
                    <input type="checkbox" checked={chosen.has(s.id)} onChange={() => toggleSource(s.id)} />
                    <span title={s.title}>{s.title}</span>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </div>

        <Segmented label="Script" value={script} options={SCRIPTS} onChange={setScript} />

        <label className="check check--quiet">
          <input type="checkbox" checked={fresh} onChange={(e) => setFresh(e.target.checked)} />
          Always make a new quiz, even if I already have one with these settings
        </label>

        <Button type="submit" disabled={!canSubmit}>
          {busy ? <span className="spinner" /> : 'Generate quiz'}
        </Button>
      </form>
    </Modal>
  )
}
