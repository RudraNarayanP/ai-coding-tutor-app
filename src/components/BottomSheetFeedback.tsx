import React, { useEffect } from 'react'
import { PatchworkCharacter } from './PatchworkCharacters'
import { playPatchworkSound } from '../utils/audio'

interface BottomSheetFeedbackProps {
  isOpen: boolean
  isCorrect: boolean
  title?: string
  explanation?: string
  correctAnswer?: string
  xpReward?: number
  onContinue: () => void
  soundEnabled?: boolean
}

export const BottomSheetFeedback: React.FC<BottomSheetFeedbackProps> = ({
  isOpen,
  isCorrect,
  title,
  explanation,
  correctAnswer,
  xpReward = 10,
  onContinue,
  soundEnabled = true,
}) => {
  useEffect(() => {
    if (isOpen) {
      if (soundEnabled) {
        playPatchworkSound(isCorrect ? 'correct_chime' : 'error')
      }
    }
  }, [isOpen, isCorrect, soundEnabled])

  if (!isOpen) return null

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      onContinue()
    }
  }

  return (
    <div
      className={`bottom-sheet-overlay ${isOpen ? 'open' : ''}`}
      onKeyDown={handleKeyDown}
      tabIndex={0}
      role="dialog"
      aria-label="Exercise Result"
    >
      <div className={`bottom-sheet-card ${isCorrect ? 'correct' : 'incorrect'}`}>
        <div className="bottom-sheet-header">
          <div className="bottom-sheet-avatar">
            <PatchworkCharacter name="patch" state={isCorrect ? 'celebrate' : 'thinking'} size={60} />
          </div>
          <div className="bottom-sheet-title-group">
            <div className="bottom-sheet-badge">
              {isCorrect ? '🎉 EXCELLENT!' : '💡 ALMOST THERE'}
            </div>
            <h2 className="bottom-sheet-title">
              {title || (isCorrect ? 'Nice job!' : 'Not quite right')}
            </h2>
          </div>
          {isCorrect && xpReward > 0 && (
            <div className="xp-pop-badge">+ {xpReward} XP</div>
          )}
        </div>

        <div className="bottom-sheet-body">
          {!isCorrect && correctAnswer && (
            <div className="correct-answer-callout">
              <span className="callout-label">Correct answer:</span>
              <code className="callout-code">{correctAnswer}</code>
            </div>
          )}
          {explanation && <p className="bottom-sheet-explanation">{explanation}</p>}
        </div>

        <div className="bottom-sheet-footer">
          <button
            type="button"
            className={`duo-button bottom-sheet-continue-btn ${isCorrect ? 'duo-button-success' : 'duo-button-danger'}`}
            onClick={onContinue}
            autoFocus
          >
            CONTINUE
          </button>
        </div>
      </div>
    </div>
  )
}

export default BottomSheetFeedback
