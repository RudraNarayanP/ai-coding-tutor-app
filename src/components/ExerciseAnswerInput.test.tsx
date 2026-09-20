import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import answerOrderFixture from '../../fixtures/answer_order.json'
import { ExerciseAnswerInput, orderedOptions } from './ExerciseAnswerInput'

// Captured verbatim from `GET /api/lessons/pytest-testing-01` on the running
// server, so the ordering widget is exercised against the payload learners
// actually receive rather than a hand-written stand-in.
const REAL_ORDERING_EXERCISE = {
  id: 'pytest-testing-01-order-1',
  type: 'ordering',
  question:
    'Put the steps of `3. Fixture-like Setup (Concept Challenge)` back in order. Each line depends on the one before it.',
  options: ['return data', 'data = factory()', 'callback(data)', 'data.clear()'],
  xp_reward: 10,
}

describe('orderedOptions', () => {
  const options = ['alpha', 'beta', 'gamma', 'delta']

  it('keeps every option exactly once', () => {
    const out = orderedOptions('py-ex-1a', options)
    expect([...out].sort()).toEqual([...options].sort())
  })

  it('is stable for the same exercise id', () => {
    expect(orderedOptions('py-ex-1a', options)).toEqual(orderedOptions('py-ex-1a', options))
  })

  it('does not leave every exercise in stored order', () => {
    const ids = ['cpp-ex-1a', 'cpp-ex-1b', 'java-ex-1a', 'py-ex-1a', 'sql-ex-1a', 'js-ex-1']
    const firsts = new Set(ids.map((id) => orderedOptions(id, options)[0]))
    expect(firsts.size).toBeGreaterThan(1)
  })

  it('leaves two-option lists untouched', () => {
    expect(orderedOptions('x', ['True', 'False'])).toEqual(['True', 'False'])
  })

  it('handles empty input', () => {
    expect(orderedOptions('x', [])).toEqual([])
  })

  // fixtures/answer_order.json is asserted by backend/test_answer_order.py too:
  // the Python mirror that gates curriculum content must agree with this
  // function, on the same cases, or the gate is checking something learners
  // never see. Regenerate it by running this function over the curriculum's
  // option lists in Node.
  it.each(answerOrderFixture)('matches the pinned contract for $id', (fixture) => {
    expect(orderedOptions(fixture.id, fixture.options)).toEqual(fixture.displayed)
  })
})

describe('ordering widget', () => {
  const baseProps = {
    exercise: REAL_ORDERING_EXERCISE,
    exType: 'ordering',
    exState: {},
    disabled: false,
  }

  it('renders every step as a tappable block and asks for an order', () => {
    render(<ExerciseAnswerInput {...baseProps} setState={() => {}} />)
    expect(screen.getByText('Tap the blocks below in the correct order…')).toBeInTheDocument()
    for (const option of REAL_ORDERING_EXERCISE.options) {
      expect(screen.getByRole('button', { name: option })).toBeInTheDocument()
    }
  })

  it('builds a sequence across taps, in the order tapped', () => {
    // The widget is controlled: `order` lives in the parent, so drive it the
    // way the app does rather than asserting on isolated callbacks.
    const setState = vi.fn()
    const first = render(<ExerciseAnswerInput {...baseProps} setState={setState} />)

    fireEvent.click(first.getByRole('button', { name: 'data = factory()' }))
    expect(setState).toHaveBeenLastCalledWith({ order: ['data = factory()'] })

    first.unmount()
    const second = render(
      <ExerciseAnswerInput
        {...baseProps}
        exState={{ order: ['data = factory()'] }}
        setState={setState}
      />
    )
    fireEvent.click(second.getByRole('button', { name: 'return data' }))
    expect(setState).toHaveBeenLastCalledWith({ order: ['data = factory()', 'return data'] })
  })

  it('shows the placed sequence numbered and lets a mistake be undone', () => {
    const setState = vi.fn()
    render(
      <ExerciseAnswerInput
        {...baseProps}
        exState={{ order: ['data = factory()', 'callback(data)'] }}
        setState={setState}
      />
    )

    expect(screen.getByLabelText('Your sequence')).toHaveTextContent('1. data = factory()')
    expect(screen.getByLabelText('Your sequence')).toHaveTextContent('2. callback(data)')

    fireEvent.click(screen.getByRole('button', { name: 'Remove callback(data) from sequence' }))
    expect(setState).toHaveBeenLastCalledWith({ order: ['data = factory()'] })
  })

  it('only offers unplaced blocks, so a step cannot be used twice', () => {
    render(
      <ExerciseAnswerInput
        {...baseProps}
        exState={{ order: ['return data'] }}
        setState={() => {}}
      />
    )
    expect(screen.queryByRole('button', { name: 'return data' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'data.clear()' })).toBeInTheDocument()
  })
})
