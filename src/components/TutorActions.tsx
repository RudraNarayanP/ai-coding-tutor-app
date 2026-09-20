/**
 * TutorActions — the hint / answer / restore row.
 *
 * Extracted so every workspace renders the SAME affordance vocabulary:
 * the lightbulb belongs to the hint, the answer is spelled out and needs a
 * second confirming tap, and pasting an answer is always reversible.
 */

export type TutorActionsProps = {
  hintDisabled: boolean
  isTutorLoading: boolean
  isAiAvailable: boolean
  aiEnabled: boolean
  answerArmed: boolean
  hasCodeToRestore: boolean
  onHint: () => void
  onAnswer: () => void
  onRestore: () => void
  answerDisabled?: boolean
  buttonClass?: string
  answerButtonClass?: string
}

export function TutorActions({
  hintDisabled,
  isTutorLoading,
  isAiAvailable,
  aiEnabled,
  answerArmed,
  hasCodeToRestore,
  onHint,
  onAnswer,
  onRestore,
  answerDisabled = false,
  buttonClass = 'duo-button duo-button-secondary',
  answerButtonClass = 'duo-button duo-button-secondary duo-button-solution',
}: TutorActionsProps) {
  const hintLabel = !isAiAvailable
    ? 'AI tutor unavailable'
    : !aiEnabled
      ? 'AI tutor is paused'
      : 'Request a hint'

  return (
    <>
      <button
        id="hint-button"
        className={buttonClass}
        onClick={onHint}
        disabled={hintDisabled}
        aria-label={hintLabel}
        title="A short nudge — never the answer"
      >
        {isTutorLoading ? 'Getting Hint…' : `💡 ${hintLabel}`}
      </button>

      {hasCodeToRestore ? (
        <button
          id="restore-code-button"
          className={buttonClass}
          onClick={onRestore}
          aria-label="Restore my code"
          title="Put your own code back in the editor"
        >
          ↩ Restore my code
        </button>
      ) : null}

      <button
        id="solution-button"
        className={`${answerButtonClass}${answerArmed ? ' ew-btn--armed' : ''}`}
        onClick={onAnswer}
        disabled={answerDisabled}
        aria-label={answerArmed ? 'Confirm: paste the complete answer' : 'Show full answer'}
        title="Pastes the finished solution into the editor"
      >
        {answerArmed ? '⚠ Yes, paste the answer' : 'Show full answer'}
      </button>
    </>
  )
}
