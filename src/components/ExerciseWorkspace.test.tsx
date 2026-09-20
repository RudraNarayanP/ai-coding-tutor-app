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

  it('builds numbered steps without revealing the blank answer', () => {
    expect(getTaskSteps(cinemaExercise)).toEqual([
      'Multiplication (*) calculates the total cost of multiple identical items.',
      'Fill the blank in the code above.',
      'Multiplication gives us $36 for 3 tickets.',
    ])
  })

  it('never quotes blanks[] or correct_answer in the task steps', () => {
    const steps = getTaskSteps(cinemaExercise)
    expect(steps.join(' ')).not.toContain('num_tickets')
    const multi = { ...cinemaExercise, blanks: ['num_tickets', 'ticket_price'] }
    expect(getTaskSteps(multi)).toContain('Fill 2 blanks in the code above.')
  })

  it('still says how many blanks to fill when the payload omits blanks', () => {
    // The server strips `blanks` because it is the answer key, so the count
    // must come from the rendered template instead.
    const { blanks: _blanks, ...serverShape } = cinemaExercise
    const steps = getTaskSteps(serverShape, 1)
    expect(steps).toContain('Fill the blank in the code above.')
    expect(getTaskSteps(serverShape, 2)).toContain('Fill 2 blanks in the code above.')
    expect(getTaskSteps(serverShape, 0)).not.toContain('Fill the blank in the code above.')
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
    expect(screen.getByText(/Fill the blank in the code above/)).toBeInTheDocument()
    expect(screen.queryByText(/Fill in the blank with/)).not.toBeInTheDocument()
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

const mcqExercise = {
  id: 'js-ex-1',
  type: 'mcq',
  question: 'Which keyword declares a block-scoped variable in JavaScript?',
  options: ['var', 'let', 'function', 'static'],
  correct_answer: 'let',
}

describe('ExerciseWorkspace non-code exercises', () => {
  it('renders the answer card for an MCQ without the code editor or RUN button', () => {
    render(
      <ExerciseWorkspace
        {...workspaceProps}
        exercise={mcqExercise}
        exType="mcq"
        onRun={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: 'Exit exercise' })).toBeInTheDocument()
    expect(screen.getByText('Which keyword declares a block-scoped variable in JavaScript?')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'let' })).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Code editor' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /RUN/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'SUBMIT' })).toBeInTheDocument()
  })

  it('records the picked option through onInputChange', () => {
    const onInputChange = vi.fn()
    render(
      <ExerciseWorkspace
        {...workspaceProps}
        exercise={mcqExercise}
        exType="mcq"
        onInputChange={onInputChange}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: 'let' }))
    const updater = onInputChange.mock.calls[0][0]
    expect(updater({})['js-ex-1'].answer).toBe('let')
  })
})

const lessonExercise = {
  id: 'lesson-ml-1',
  type: 'code',
  question: 'Implement `predict(x, w, b)` = w*x + b for scalars.',
  sublessonTitle: '1. Linear Prediction',
  starter_code: 'def predict(x, w, b):\n    # TODO\n    pass',
}

describe('ExerciseWorkspace lesson mode', () => {
  const lessonProps = {
    exercise: lessonExercise,
    exType: 'code',
    exerciseInput: { 'lesson-ml-1': { code: lessonExercise.starter_code } },
    exercisePhase: 'answering',
    exerciseFeedback: null,
    exercisePosition: 1,
    exerciseTotal: 1,
    completedExerciseCount: 0,
    onInputChange: vi.fn(),
    onContinue: vi.fn(),
    onRetry: vi.fn(),
    onRun: vi.fn(),
    onBack: vi.fn(),
    soundEnabled: true,
    onToggleSound: vi.fn(),
    onOpenGuidebook: vi.fn(),
  }

  it('shows the plain lesson title, lesson-mode footer actions, and slot content', () => {
    render(
      <ExerciseWorkspace
        {...lessonProps}
        lessonMode
        editorFilename="exercise.py"
        footerExtra={<button type="button">Request a hint</button>}
        taskExtra={<div>Session notes</div>}
        outputExtra={<div role="region" aria-label="Test results">All 3 tests passed</div>}
        banner={<div>🎉 Lesson Complete!</div>}
      />
    )

    expect(screen.getByRole('heading', { level: 2, name: '1. Linear Prediction' })).toBeInTheDocument()
    expect(screen.queryByRole('progressbar', { name: 'Lesson progress' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back to Map' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Request a hint' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run code' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Guidebook/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'SUBMIT' })).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Code editor' })).toHaveValue(lessonExercise.starter_code)
    expect(screen.getByText('Session notes')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Test results' })).toBeInTheDocument()
    expect(screen.getByText('🎉 Lesson Complete!')).toBeInTheDocument()
  })
})

describe('ordering exercise wiring', () => {
  // Captured from `GET /api/lessons/pytest-testing-01` on the running server:
  // this is the payload a learner receives, which carries no answer key.
  const orderingExercise = {
    id: 'pytest-testing-01-order-1',
    type: 'ordering',
    title: '',
    question:
      'Put the steps of `3. Fixture-like Setup (Concept Challenge)` back in order. Each line depends on the one before it.',
    micro_explanation: '',
    worked_example: '',
    worked_example_takeaway: '',
    deep_dive: '',
    options: ['return data', 'data = factory()', 'callback(data)', 'data.clear()'],
    pairs: [],
    starter_code: '',
    hints: [],
    xp_reward: 10,
  }

  it('renders the sequencing widget instead of a code editor', () => {
    render(
      <ExerciseWorkspace
        {...workspaceProps}
        exercise={orderingExercise}
        exType="ordering"
        exerciseTotal={1}
      />
    )

    expect(screen.getByText('Tap the blocks below in the correct order…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'data = factory()' })).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Code editor' })).not.toBeInTheDocument()
  })

  it('does not surface an answer key that the payload never contained', () => {
    render(
      <ExerciseWorkspace
        {...workspaceProps}
        exercise={orderingExercise}
        exType="ordering"
        exerciseTotal={1}
      />
    )
    const body = document.body.textContent || ''
    // The canonical order is `data = factory()` first; the served options put
    // `return data` first, so nothing on screen states the solution order.
    expect(body).not.toContain('correct_answer')
    expect(screen.queryByText(/1\. data = factory\(\)/)).not.toBeInTheDocument()
  })

  it('submits the tapped sequence as an order payload', () => {
    const onSubmit = vi.fn()
    render(
      <ExerciseWorkspace
        {...workspaceProps}
        exercise={orderingExercise}
        exType="ordering"
        exerciseTotal={1}
        exerciseInput={{ [orderingExercise.id]: { order: ['data = factory()'] } }}
        onSubmit={onSubmit}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: 'SUBMIT' }))
    expect(onSubmit).toHaveBeenCalled()
  })
})
