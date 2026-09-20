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

  it.each([
    ['javascript', 'calculate_ticket_total.js'],
    ['typescript', 'calculate_ticket_total.ts'],
    ['java', 'calculate_ticket_total.java'],
    ['cpp', 'calculate_ticket_total.cpp'],
    ['sql', 'calculate_ticket_total.sql'],
    ['python', 'calculate_ticket_total.py'],
  ])('names the editor after the %s course, never a fixed .py', (language, expected) => {
    render(
      <ExercisePanel
        exercise={fillExercise}
        exerciseInput={{}}
        exercisePhase="answering"
        exerciseFeedback={null}
        exercisePosition={1}
        exerciseTotal={2}
        completedExerciseCount={0}
        onInputChange={vi.fn()}
        onSubmit={vi.fn()}
        onContinue={vi.fn()}
        onRetry={vi.fn()}
        language={language}
      />
    )
    expect(screen.getByText(expected)).toBeInTheDocument()
  })
})

describe('ExercisePanel fullscreen delegation', () => {
  it('passes the tutor chrome through to the fullscreen workspace', () => {
    render(
      <ExercisePanel
        exercise={fillExercise}
        exerciseInput={{}}
        exercisePhase="answering"
        exerciseFeedback={null}
        exercisePosition={1}
        exerciseTotal={2}
        completedExerciseCount={0}
        onInputChange={vi.fn()}
        onSubmit={vi.fn()}
        onContinue={vi.fn()}
        onRetry={vi.fn()}
        onBack={vi.fn()}
        footerExtra={<button type="button">💡 Request a hint</button>}
        outputExtra={<div data-testid="tutor-box">A short nudge.</div>}
      />
    )

    // Exercise steps used to render no tutor affordance at all.
    expect(screen.getByRole('button', { name: /Request a hint/ })).toBeInTheDocument()
    expect(screen.getByTestId('tutor-box')).toBeInTheDocument()
  })

  it('opens the fullscreen workspace for an MCQ exercise when onBack is provided', () => {
    render(
      <ExercisePanel
        exercise={{
          id: 'js-ex-1',
          type: 'mcq',
          question: 'Which keyword declares a block-scoped variable in JavaScript?',
          options: ['var', 'let', 'function', 'static'],
          correct_answer: 'let',
        }}
        exerciseInput={{}}
        exercisePhase="answering"
        exerciseFeedback={null}
        exercisePosition={1}
        exerciseTotal={2}
        completedExerciseCount={0}
        onInputChange={vi.fn()}
        onSubmit={vi.fn()}
        onContinue={vi.fn()}
        onRetry={vi.fn()}
        onBack={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: 'Exit exercise' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'let' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'SUBMIT' })).toBeInTheDocument()
  })
})
