import { PatchworkCharacter } from '../components/PatchworkCharacters'
import { HintText } from './rich'
import type { Exercise } from './types'

export function FeedbackSheet({
  correct,
  xp,
  message,
  answer,
  explanation,
  onContinue,
}: {
  correct: boolean
  xp: number
  message: string
  answer?: string
  explanation: string
  onContinue: () => void
}) {
  return (
    <div className={`lp-sheet${correct ? ' is-correct' : ' is-wrong'}`} role="status">
      <div className="lp-sheet-copy">
        <PatchworkCharacter name="patch" state={correct ? 'celebrate' : 'encouraging'} size={56} />
        <div>
          <p className="lp-sheet-title">{correct ? message : 'Not quite.'}</p>
          {correct && xp > 0 ? <p className="lp-xp-pop">+{xp} XP</p> : null}
          {!correct && answer ? (
            <p>
              Correct answer: <HintText value={answer} />
            </p>
          ) : null}
          {!correct ? <p>{explanation}</p> : null}
        </div>
      </div>
      <button type="button" className="lp-btn lp-btn-sheet" onClick={onContinue}>
        Continue
      </button>
    </div>
  )
}

export function displayAnswer(exercise: Exercise): string {
  if (Array.isArray(exercise.answer)) return exercise.answer.join(' ')
  if (exercise.type === 'spot_the_bug') return `Line ${exercise.answer}`
  if (exercise.type === 'write_code') return exercise.hints[2]
  return exercise.answer
}
