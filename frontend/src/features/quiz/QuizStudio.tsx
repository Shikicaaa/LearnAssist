import { useState } from 'react'
import { describeError } from '../../lib/api/client'
import type { Artifact, Source } from '../../lib/api/types'
import { ChevronRightIcon, PlusIcon, QuizIcon, RetryIcon, TrashIcon } from '../../components/ui'
import { QuizPlayer } from './QuizPlayer'
import { QuizSetupModal } from './QuizSetupModal'
import { useQuizzes } from './useQuizzes'
import './quiz.css'

function rowTitle(quiz: Artifact) {
  return quiz.params.topic ?? 'Whole material'
}

function rowMeta(quiz: Artifact) {
  const { num_questions: n, difficulty } = quiz.params
  return `${n} questions · ${difficulty}`
}

/** NotebookLM-style "Studio": things generated from the sources. For now, quizzes. */
export function QuizStudio({ sid, sources }: { sid: string; sources: Source[] }) {
  const { quizzes, loading, generate, remove } = useQuizzes(sid)
  const [setupOpen, setSetupOpen] = useState(false)
  const [playing, setPlaying] = useState<Artifact | null>(null)
  const [error, setError] = useState<string | null>(null)

  const ready = sources.filter((s) => s.status === 'ready')
  const blocked = ready.length === 0

  function onCreated(quiz: Artifact) {
    setSetupOpen(false)
    if (quiz.status === 'ready') setPlaying(quiz) // already stored for these settings: no waiting
  }

  async function run(action: () => Promise<unknown>) {
    setError(null)
    try {
      await action()
    } catch (err) {
      setError(describeError(err))
    }
  }

  /** The same request again: the backend starts a failed quiz over. */
  const retry = (quiz: Artifact) =>
    run(() =>
      generate({
        topic: quiz.params.topic,
        source_ids: quiz.params.source_ids,
        num_questions: quiz.params.num_questions,
        difficulty: quiz.params.difficulty,
        types: quiz.params.types,
        script: quiz.params.script,
      }),
    )

  return (
    <section className="studio" aria-label="Studio">
      <div className="studio__head">
        <h2>Studio</h2>
      </div>

      <button
        className="studio__tile"
        onClick={() => setSetupOpen(true)}
        disabled={blocked}
        title={blocked ? 'Add a source first' : undefined}
      >
        <span className="studio__icon">
          <QuizIcon />
        </span>
        <span className="studio__tile-text">
          <strong>Quiz</strong>
          <small>{blocked ? 'Add a source first' : 'Test yourself on your sources'}</small>
        </span>
        <PlusIcon size={16} />
      </button>

      {error && (
        <div className="alert" role="alert">
          {error}
        </div>
      )}

      {!loading && quizzes.length > 0 && (
        <ul className="studio__list">
          {quizzes.map((quiz) => (
            <li key={quiz.id} className={`quizrow quizrow--${quiz.status}`}>
              <button
                className="quizrow__main"
                disabled={quiz.status !== 'ready'}
                onClick={() => setPlaying(quiz)}
                aria-label={`Open quiz: ${rowTitle(quiz)}`}
              >
                <span className="quizrow__title" title={rowTitle(quiz)}>
                  {rowTitle(quiz)}
                </span>
                <span className="quizrow__meta mono">
                  {quiz.status === 'pending' && (
                    <span className="pill">
                      <span className="spinner" />
                      Generating…
                    </span>
                  )}
                  {quiz.status === 'failed' && <span className="pill pill--failed">Failed</span>}
                  {rowMeta(quiz)}
                </span>
                {quiz.status === 'failed' && quiz.error && <span className="quizrow__error">{quiz.error}</span>}
              </button>
              {quiz.status === 'ready' && <ChevronRightIcon size={16} />}
              {quiz.status === 'failed' && (
                <button className="icon-btn" onClick={() => void retry(quiz)} aria-label="Try again" title="Try again">
                  <RetryIcon size={16} />
                </button>
              )}
              <button
                className="icon-btn"
                onClick={() => void run(() => remove(quiz.id))}
                aria-label="Delete quiz"
                title="Delete quiz"
              >
                <TrashIcon size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}

      {setupOpen && (
        <QuizSetupModal sources={ready} onClose={() => setSetupOpen(false)} onGenerate={generate} onCreated={onCreated} />
      )}
      {playing && <QuizPlayer quiz={playing} onClose={() => setPlaying(null)} />}
    </section>
  )
}
