import React, { useState } from 'react'
import { api } from '../api'

interface ExerciseFeedbackProps {
  exerciseId: string
  lessonId?: string | null
  /** When true (e.g. after a wrong answer), only offer REPORT. */
  reportOnly?: boolean
}

type Rating = 'too_easy' | 'too_difficult' | 'report'

/**
 * Duolingo-style exercise feedback row.
 *
 * After an answer is graded the learner can flag the exercise as TOO EASY /
 * TOO DIFFICULT or REPORT a problem. Ratings are persisted server-side and
 * immediately steer subsequent AI tutor responses for this learner.
 */
export const ExerciseFeedback: React.FC<ExerciseFeedbackProps> = ({
  exerciseId,
  lessonId,
  reportOnly = false,
}) => {
  const [ack, setAck] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [reportOpen, setReportOpen] = useState(false)
  const [comment, setComment] = useState('')
  const [error, setError] = useState<string | null>(null)

  const send = async (rating: Rating, text?: string) => {
    if (sending || ack) return
    setSending(true)
    setError(null)
    try {
      const res = await api.submitFeedback({
        exercise_id: exerciseId,
        lesson_id: lessonId ?? null,
        rating,
        comment: text || undefined,
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setAck(data.adaptation || 'Thanks for the feedback!')
      setReportOpen(false)
    } catch (err) {
      console.error('Failed to submit exercise feedback:', err)
      setError('Could not save feedback — the tutor keeps its current style.')
    } finally {
      setSending(false)
    }
  }

  if (ack) {
    return (
      <div className="exercise-feedback-ack" role="status">
        <span aria-hidden="true">✓</span> {ack}
      </div>
    )
  }

  return (
    <div className="exercise-feedback-row">
      {!reportOnly && (
        <>
          <button
            type="button"
            className="exercise-feedback-btn"
            disabled={sending}
            onClick={() => send('too_easy')}
            aria-label="This exercise felt too easy"
          >
            ⚡ Too easy
          </button>
          <button
            type="button"
            className="exercise-feedback-btn"
            disabled={sending}
            onClick={() => send('too_difficult')}
            aria-label="This exercise felt too difficult"
          >
            🧱 Too difficult
          </button>
        </>
      )}
      {!reportOpen ? (
        <button
          type="button"
          className="exercise-feedback-btn exercise-feedback-report"
          disabled={sending}
          onClick={() => setReportOpen(true)}
          aria-label="Report a problem with this exercise"
        >
          🚩 Report
        </button>
      ) : (
        <div className="exercise-feedback-report-form">
          <input
            type="text"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="What went wrong? (optional)"
            aria-label="Report details"
            disabled={sending}
            className="exercise-feedback-report-input"
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                send('report', comment)
              }
            }}
          />
          <button
            type="button"
            className="duo-button duo-button-primary exercise-feedback-send"
            disabled={sending}
            onClick={() => send('report', comment)}
          >
            {sending ? 'Sending…' : 'Send'}
          </button>
          <button
            type="button"
            className="duo-button duo-button-secondary exercise-feedback-send"
            disabled={sending}
            onClick={() => {
              setReportOpen(false)
              setComment('')
            }}
          >
            Cancel
          </button>
        </div>
      )}
      {error && (
        <div className="exercise-feedback-error" role="alert">
          {error}
        </div>
      )}
    </div>
  )
}

export default ExerciseFeedback
