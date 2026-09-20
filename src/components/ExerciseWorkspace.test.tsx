import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ExerciseWorkspace, {
  exerciseFilename,
  formatTaskTitle,
  getTaskSteps,
} from './ExerciseWorkspace'

const cinemaExercise = {
  id: 'cinema-ex-1a',
  type: 'fill_blank',
  question: '3 tickets cost $12 each. Calculate ticket_total using multiplication:',
  sublessonTitle: 'Step A: Calculate Ticket Total',
  micro_explanation: 'Multiplication (*) calculates the total cost of multiple identical items.',
  worked_example_takeaway: 'Multiplication gives us $36 for 3 tickets.',
  starter_code: 'ticket_price = 12\nnum_tickets = 3\nticket_total = ticket_price * num_tickets',
  blanks: ['num_tickets'],
}

const workspaceProps = {
  exercise: cinemaExercise,
  exType: 'fill_blank',
  exerciseInput: {},
  exercisePhase: 'answering',
  exerciseFeedback: null,
  exercisePosition: 1,
  exerciseTotal: 2,
  completedExerciseCount: 0,
  onInputChange: vi.fn(),
  onSubmit: vi.fn(),
  onContinue: vi.fn(),
  onRetry: vi.fn(),
  onRun: vi.fn(),
  onBack: vi.fn(),
  soundEnabled: true,
  onToggleSound: vi.fn(),
}

describe('exercise workspace copy', () => {
  it('uses the sublesson title instead of dumping the full question', () => {
    expect(formatTaskTitle(cinemaExercise, 1)).toBe('Step 1: Calculate Ticket Total')
  })

  it('builds numbered steps from explanation, blanks, and takeaway', () => {
    expect(getTaskSteps(cinemaExercise)).toEqual([
      'Multiplication (*) calculates the total cost of multiple identical items.',
      'Fill in the blank with `num_tickets`.',
      'Multiplication gives us $36 for 3 tickets.',
    ])
  })

  it('names the editor tab from the short task title', () => {
    expect(exerciseFilename(cinemaExercise)).toBe('calculate_ticket_total.py')
  })
})

describe('ExerciseWorkspace', () => {
  it('renders the reference workspace chrome for a fill-blank exercise', () => {
    render(<ExerciseWorkspace {...workspaceProps} />)

    expect(screen.getByText('YOUR TASK')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Step 1: Calculate Ticket Total' })).toBeInTheDocument()
    expect(screen.getByText(/3 tickets cost \$12 each/)).toBeInTheDocument()
    expect(screen.getByText(/Fill in the blank with/)).toBeInTheDocument()
    expect(screen.getByText('num_tickets')).toBeInTheDocument()
    expect(screen.getByText('calculate_ticket_total.py')).toBeInTheDocument()
    const editor = screen.getByRole('textbox', { name: 'Code editor' })
    expect(editor).toBeEnabled()
    expect(editor).toHaveValue(
      'ticket_price = 12\nnum_tickets = 3\nticket_total = ticket_price * '
    )
    expect(screen.queryByLabelText('Blank 1')).not.toBeInTheDocument()
    expect(screen.queryByText('___')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'BACK' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'RUN' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'SUBMIT' })).toBeInTheDocument()
  })

  it('lets the learner type anywhere in the fill-blank editor', () => {
    const onInputChange = vi.fn()
    render(<ExerciseWorkspace {...workspaceProps} onInputChange={onInputChange} />)

    fireEvent.change(screen.getByRole('textbox', { name: 'Code editor' }), {
      target: {
        value:
          'ticket_price = 12\nnum_tickets = 3\nticket_total = ticket_price * num_tickets\nprint(ticket_total)',
      },
    })

    expect(onInputChange).toHaveBeenCalled()
    const updater = onInputChange.mock.calls[0][0]
    expect(updater({})[cinemaExercise.id].code).toContain('print(ticket_total)')
    expect(updater({})[cinemaExercise.id].answers).toEqual(['num_tickets\nprint(ticket_total)'])
  })
})
