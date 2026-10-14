import { useState } from 'react'

const REVIEW = {
  prompt: 'What is not False?',
  options: ['True', 'False', 'Error'],
  answer: 'True',
}

/** A short review that can earn one heart. It never locks the learner out. */
export function HeartPractice({ onDone }: { onDone: (earned: boolean) => void }) {
  const [choice, setChoice] = useState<string | null>(null)
  const [checked, setChecked] = useState(false)
  const earned = choice === REVIEW.answer

  return (
    <div className="lp-practice" role="dialog" aria-label="Practice to earn a heart">
      <div className="lp-practice-card">
        <h2>Practice to earn a heart</h2>
        <p>{REVIEW.prompt}</p>
        <div className="lp-options">
          {REVIEW.options.map((option) => (
            <button
              key={option}
              type="button"
              className={`lp-option${choice === option ? ' is-selected' : ''}`}
              aria-pressed={choice === option}
              onClick={() => {
                if (!checked) setChoice(option)
              }}
            >
              {option}
            </button>
          ))}
        </div>
        {checked ? <p>{earned ? 'Heart earned.' : 'Keep going. You can earn a heart next time.'}</p> : null}
        {!checked ? (
          <button type="button" className="lp-btn lp-btn-primary" disabled={!choice} onClick={() => setChecked(true)}>
            Check
          </button>
        ) : (
          <button type="button" className="lp-btn lp-btn-primary" onClick={() => onDone(earned)}>
            Continue
          </button>
        )}
      </div>
    </div>
  )
}
