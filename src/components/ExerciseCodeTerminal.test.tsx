import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { ExerciseCodeTerminal } from './ExerciseCodeTerminal'

describe('ExerciseCodeTerminal', () => {
  it('renders code with inline blanks in a terminal', () => {
    render(
      <ExerciseCodeTerminal
        code="ticket_price = 12\nnum_tickets = 3\nticket_total = ticket_price * ___"
        answers={[]}
        onAnswerChange={() => {}}
      />
    )

    expect(screen.getByLabelText('Code terminal')).toBeInTheDocument()
    expect(screen.getByText(/ticket_price = 12/)).toBeInTheDocument()
    expect(screen.getByLabelText('Blank 1')).toBeInTheDocument()
    expect(screen.queryByText(/Blank 1:/)).not.toBeInTheDocument()
  })

  it('calls onRun when Shift+Enter is pressed in a blank', async () => {
    const user = userEvent.setup()
    const onRun = vi.fn()

    render(
      <ExerciseCodeTerminal
        code="ticket_total = ticket_price * ___"
        answers={['num_tickets']}
        onAnswerChange={() => {}}
        onRun={onRun}
      />
    )

    const blank = screen.getByLabelText('Blank 1')
    await user.click(blank)
    await user.keyboard('{Shift>}{Enter}{/Shift}')
    expect(onRun).toHaveBeenCalledTimes(1)
  })

  it('shows run output below the code', () => {
    render(
      <ExerciseCodeTerminal
        code="ticket_total = ticket_price * ___"
        answers={['num_tickets']}
        onAnswerChange={() => {}}
        runOutput={{ stdout: 'ticket_total = 36' }}
      />
    )

    expect(screen.getByText('ticket_total = 36')).toBeInTheDocument()
  })
})
