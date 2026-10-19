import { useState } from 'react'
import type { Artifact, Citation, QuizQuestion } from '../../lib/api/types'
import { Button, CheckIcon, CloseIcon, Modal } from '../../components/ui'
import { CitationModal } from '../chat/CitationModal'
import { MarkdownMessage } from '../chat/MarkdownMessage'

const LETTERS = 'ABCDEFGH'
const noCitationClick = () => {}

/** What the user did with one question. `picked` is the option index (null for short answers). */
interface Result {
  picked: number | null
  correct: boolean
}

/** The model writes Markdown and LaTeX, so questions and options go through the same renderer. */
function Rich({ text }: { text: string }) {
  return <MarkdownMessage content={text} citations={[]} onCitation={noCitationClick} />
}

function toCitation(q: QuizQuestion, rank: number): Citation {
  const c = q.citation
  return {
    rank,
    chunk_id: c.chunk_id,
    source_id: c.source_id,
    source_title: c.source_title,
    page_start: c.page_start,
    page_end: c.page_end,
    score: 1,
  }
}

function pagesLabel(q: QuizQuestion) {
  const { page_start: from, page_end: to } = q.citation
  if (from == null) return null
  return to && to !== from ? `pp. ${from}–${to}` : `p. ${from}`
}

export function QuizPlayer({ quiz, onClose }: { quiz: Artifact; onClose: () => void }) {
  const questions = quiz.content?.questions ?? []
  const [index, setIndex] = useState(0)
  const [results, setResults] = useState<Result[]>([])
  const [revealed, setRevealed] = useState(false) // short answers: the correct answer is shown
  const [finished, setFinished] = useState(false)
  const [source, setSource] = useState<Citation | null>(null)

  const question = questions[index]
  const result = results[index] as Result | undefined // set once the question is answered
  const score = results.filter((r) => r.correct).length

  function record(next: Result) {
    setResults((list) => {
      const copy = [...list]
      copy[index] = next
      return copy
    })
  }

  function advance() {
    setRevealed(false)
    if (index + 1 < questions.length) setIndex(index + 1)
    else setFinished(true)
  }

  function restart() {
    setIndex(0)
    setResults([])
    setRevealed(false)
    setFinished(false)
  }

  const title = `Quiz · ${questions.length} questions`

  if (questions.length === 0) {
    return (
      <Modal title="Quiz" onClose={onClose}>
        <p style={{ color: 'var(--text-dim)' }}>This quiz has no questions.</p>
      </Modal>
    )
  }

  if (finished) {
    const percent = Math.round((score / questions.length) * 100)
    return (
      <Modal title="Your result" onClose={onClose} size="lg">
        <div className="quiz-score">
          <div className="quiz-score__num">
            {score}
            <span> / {questions.length}</span>
          </div>
          <div className="quiz-score__bar" aria-hidden="true">
            <span style={{ width: `${percent}%` }} />
          </div>
          <p className="quiz-score__msg">
            {percent === 100 ? 'Perfect!' : percent >= 70 ? 'Nicely done.' : percent >= 40 ? 'Getting there.' : 'Worth another read of your sources.'}
          </p>
        </div>

        <ol className="quiz-review">
          {questions.map((q, i) => {
            const r = results[i]
            return (
              <li key={i} className={r?.correct ? 'is-right' : 'is-wrong'}>
                <span className="quiz-review__mark">{r?.correct ? <CheckIcon size={16} /> : <CloseIcon size={16} />}</span>
                <div className="quiz-review__text">
                  <Rich text={q.question} />
                  {!r?.correct && (
                    <p className="quiz-review__answer">
                      Answer: <Rich text={q.type === 'short_answer' ? (q.correct_answer ?? '') : (q.options[q.correct_index ?? 0] ?? '')} />
                    </p>
                  )}
                </div>
              </li>
            )
          })}
        </ol>

        <div className="quiz-actions">
          <Button variant="ghost" onClick={restart}>
            Try again
          </Button>
          <Button onClick={onClose}>Done</Button>
        </div>
      </Modal>
    )
  }

  const answered = result !== undefined
  const isShort = question.type === 'short_answer'

  return (
    <Modal title={title} onClose={onClose} size="lg">
      <div className="quiz-progress">
        <span className="mono">
          Question {index + 1} of {questions.length}
        </span>
        <div className="quiz-progress__bar" aria-hidden="true">
          <span style={{ width: `${((index + (answered ? 1 : 0)) / questions.length) * 100}%` }} />
        </div>
      </div>

      <div className="quiz-q">
        <Rich text={question.question} />
      </div>

      {isShort ? (
        <div className="quiz-short">
          {!revealed ? (
            <Button variant="ghost" onClick={() => setRevealed(true)}>
              Show answer
            </Button>
          ) : (
            <>
              <div className="quiz-short__answer">
                <Rich text={question.correct_answer ?? ''} />
              </div>
              {!answered && (
                <div className="quiz-actions">
                  <Button variant="ghost" onClick={() => record({ picked: null, correct: false })}>
                    I missed it
                  </Button>
                  <Button onClick={() => record({ picked: null, correct: true })}>I got it</Button>
                </div>
              )}
            </>
          )}
        </div>
      ) : (
        <div className="quiz-opts" role="group" aria-label="Answer options">
          {question.options.map((option, i) => {
            const isRight = i === question.correct_index
            const isPicked = result?.picked === i
            const state = !answered ? '' : isRight ? 'is-correct' : isPicked ? 'is-wrong' : 'is-dim'
            return (
              <button
                key={i}
                type="button"
                className={`quiz-opt ${state}`}
                disabled={answered}
                onClick={() => record({ picked: i, correct: isRight })}
              >
                <span className="quiz-opt__letter mono">{LETTERS[i]}</span>
                <span className="quiz-opt__text">
                  <Rich text={option} />
                </span>
                {answered && isRight && <CheckIcon size={18} />}
                {answered && isPicked && !isRight && <CloseIcon size={18} />}
              </button>
            )
          })}
        </div>
      )}

      {answered && (
        <div className="quiz-feedback">
          <strong className={result.correct ? 'quiz-feedback__ok' : 'quiz-feedback__no'}>
            {result.correct ? 'Correct' : 'Not quite'}
          </strong>
          <Rich text={question.explanation} />
          <blockquote className="quote">{question.evidence}</blockquote>
          <button className="quiz-source" onClick={() => setSource(toCitation(question, index + 1))}>
            {question.citation.source_title}
            {pagesLabel(question) && <span className="mono"> · {pagesLabel(question)}</span>}
          </button>
        </div>
      )}

      {answered && (
        <div className="quiz-actions">
          <Button onClick={advance}>{index + 1 < questions.length ? 'Next question' : 'See result'}</Button>
        </div>
      )}

      {source && <CitationModal citation={source} onClose={() => setSource(null)} />}
    </Modal>
  )
}
