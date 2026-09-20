import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ExercisePanel from './ExercisePanel'

const fillExercise = {
  id: 'cinema-ex-1a',
  type: 'fill_blank',
  question: 'Calculate ticket_total using multiplication:',
  starter_code: 'ticket_price = 12\nnum_tickets = 3\nticket_total = ticket_price * num_tickets',
  blanks: ['num_tickets'],
}

describe('ExercisePanel shared editor', () => {
  it('uses the full code editor for fill-blank exercises outside the fullscreen workspace', () => {
    const onInputChange = vi.fn()
    render(
      <ExercisePanel
        exercise={fillExercise}
        exerciseInput={{}}
        exercisePhase="answering"
        exerciseFeedback={null}
        exercisePosition={1}
        exerciseTotal={2}
        completedExerciseCount={0}
        onInputChange={onInputChange}
        onSubmit={vi.fn()}
        onContinue={vi.fn()}
        onRetry={vi.fn()}
      />
    )

    const editor = screen.getByRole('textbox', { name: 'Code editor' })
    expect(editor).toBeEnabled()
    expect(editor).toHaveValue(
      'ticket_price = 12\nnum_tickets = 3\nticket_total = ticket_price * '
    )
    expect(screen.queryByLabelText('Blank 1')).not.toBeInTheDocument()

    fireEvent.change(editor, {
      target: { value: 'ticket_price = 12\nnum_tickets = 3\nticket_total = ticket_price * num_tickets' },
    })
    const updater = onInputChange.mock.calls[0][0]
    expect(updater({})['cinema-ex-1a'].answers).toEqual(['num_tickets'])
  })
})
