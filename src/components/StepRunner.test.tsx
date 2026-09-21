/**
 * The ladder runner's own behaviour: what a rung asks for, what a wrong answer
 * says, and what the session ends on.
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useState } from 'react'
import { StepRunner } from './StepRunner'
import type { LadderSession, LadderStep } from '../learning/useStepSession'

function step(over: Partial<LadderStep>): LadderStep {
  return {
    id: 's-1',
    stage: 'introduce',
    widget: 'present',
    concept: 'linear-prediction',
    stakes: 'free',
    bonus: false,
    reason: 'ladder: introduce rung for linear-prediction',
    cleared: false,
    ...over,
  } as LadderStep
}

function session(steps: LadderStep[]): LadderSession {
  return {
    lesson_id: 'linreg-predict',
    skill: 'linear-prediction',
    concept: 'linear-prediction',
    objective: 'Compute a linear prediction',
    story: { why_this: 'A model turns an input into a prediction.', why_next: 'Predictions can be wrong.' },
    planned_steps: steps.length,
    bonus_steps: 0,
    steps,
    trace: steps.map((s) => `${s.stage} ${s.id}`),
    demonstrated: false,
    evidence: [],
  }
}

function baseProps(steps: LadderStep[], over: Record<string, any> = {}): Record<string, any> {
  const ladder = {
    session: session(steps),
    step: steps[0],
    index: 0,
    input: {},
    setInput: vi.fn(),
    outcome: null,
    clearOutcome: vi.fn(),
    busy: false,
    hintsUsed: 0,
    bumpHints: vi.fn(),
    advance: vi.fn(),
    markSeen: vi.fn(),
    attempt: vi.fn(),
    progress: { done: 0, total: steps.length, bonus: 0 },
    finished: false,
    onExit: vi.fn(),
    onNextLesson: vi.fn(),
    ...over,
  }
  return ladder
}

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('StepRunner', () => {
  it('opens on the idea, not on a task', () => {
    const props = baseProps([
      step({
        id: 'lp-intro',
        content: { lead: 'A model turns one input number into one prediction.',
                   symbols: { w: 'weight', b: 'bias' }, formula: 'prediction = w * x + b' },
        action: "Let's see it",
      }),
    ])
    render(<StepRunner {...(props as any)} />)

    expect(screen.getByText('A model turns one input number into one prediction.')).toBeInTheDocument()
    expect(screen.getByText('prediction = w * x + b')).toBeInTheDocument()
    expect(screen.getByText('weight')).toBeInTheDocument()
    // One primary verb, and it is not "implement".
    expect(screen.getByRole('button')).toHaveTextContent("Let's see it")
    expect(screen.queryByText(/Implement/)).not.toBeInTheDocument()
  })

  it('a presentation rung is acknowledged, and awards nothing', () => {
    const props = baseProps([step({ id: 'lp-intro', content: { lead: 'Read this.' } })])
    render(<StepRunner {...(props as any)} />)
    fireEvent.click(screen.getByText('Continue'))
    expect(props.markSeen).toHaveBeenCalledTimes(1)
  })

  it('a graded rung posts the answer, and will not submit an empty one', () => {
    const mcq = step({ id: 'lp-predict-up', stage: 'interact', widget: 'mcq',
                       question: 'x = 4, w = 3, b = 2. What is the prediction?',
                       options: ['14', '9', '6'] })

    // Nothing chosen yet: the primary action is inert rather than spending an
    // attempt on an empty answer.
    const empty = baseProps([mcq])
    render(<StepRunner {...(empty as any)} />)
    expect(screen.getByRole('button', { name: /^Check$/ })).toBeDisabled()
    cleanup()

    const answered = baseProps([mcq], { input: { answer: '14' } })
    render(<StepRunner {...(answered as any)} />)
    fireEvent.click(screen.getByRole('button', { name: /^Check$/ }))
    expect(answered.attempt).toHaveBeenCalledTimes(1)
  })

  it('a wrong answer on a free rung explains the specific mistake, not the verdict', () => {
    const props = baseProps([
      step({ id: 'lp-predict-up', stage: 'interact', widget: 'mcq', question: 'Prediction?', options: ['14', '9'] }),
    ])
    props.outcome = {
      passed: false,
      feedback: 'You shifted before scaling. Multiply first: 3 * 4, then add 2.',
      xp_awarded: 0,
      evidence: [],
      demonstrated: false,
      lesson_completed: false,
      next_lesson_id: null,
      charging: false,
    }
    render(<StepRunner {...(props as any)} />)

    expect(screen.getByText(/You shifted before scaling/)).toBeInTheDocument()
    expect(screen.getByText(/No heart at stake/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Try again$/ })).toBeInTheDocument()
  })

  it('a passed rung offers Continue and reports what it was worth', () => {
    const props = baseProps([step({ id: 'lp-fill', stage: 'scaffolded', widget: 'code_completion',
                                    question: 'Complete the body.', starter_code: 'def predict(x, w, b):\n    return w * ___ + b\n' })])
    props.outcome = { passed: true, feedback: 'Correct!', xp_awarded: 10, evidence: [],
                      demonstrated: false, lesson_completed: false, next_lesson_id: null, charging: false }
    render(<StepRunner {...(props as any)} />)

    expect(screen.getByText('+10 XP')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Continue/ }))
    expect(props.advance).toHaveBeenCalledTimes(1)
  })

  it('hints are released one rung at a time, and never run out mid-sentence', () => {
    const ladderStep = step({ id: 'lp-independent', stage: 'independent', widget: 'code',
                              question: 'Write predict().',
                              starter_code: 'def predict(x, w, b):\n    pass\n',
                              hints: ['Which name gets scaled?', 'One expression is enough.'] })

    /** The real parent: authored first, then the generated ladder, then stop. */
    function Harness() {
      const [used, setUsed] = useState(0)
      const [extra, setExtra] = useState<string[]>([])
      const bump = () => {
        if (used < 2) setUsed((n) => n + 1)
        else setExtra((list) => [...list, `Nudge ${list.length + 1}: name the value the check wants.`])
      }
      const props = baseProps([ladderStep], {
        hintsUsed: used, extraHints: extra, bumpHints: bump,
      })
      return <StepRunner {...(props as any)} />
    }

    render(<Harness />)
    expect(screen.queryByText('Which name gets scaled?')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Hint 1 of 2/ }))
    expect(screen.getByText('Which name gets scaled?')).toBeInTheDocument()
    expect(screen.queryByText('One expression is enough.')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Hint 2 of 2/ }))
    expect(screen.getByText('One expression is enough.')).toBeInTheDocument()
    // No third authored card to farm...
    expect(screen.queryByRole('button', { name: /Hint 3/ })).not.toBeInTheDocument()
    // ...but the request is not over: the tutor ladder takes it from here.
    fireEvent.click(screen.getByRole('button', { name: /Ask for a nudge \(1 of 2\)/ }))
    expect(screen.getByText(/Nudge 1/)).toBeInTheDocument()
    expect(screen.getByText('One expression is enough.')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Ask for a nudge \(2 of 2\)/ }))
    expect(screen.getByText(/Nudge 2/)).toBeInTheDocument()
    // Both ladders capped: the note appears, everything already revealed stays.
    expect(screen.getByText(/No more hints/)).toBeInTheDocument()
    expect(screen.getByText('Which name gets scaled?')).toBeInTheDocument()
  })

  it('a rung with no authored hints can still be helped', () => {
    const bare = step({ id: 'lp-fill', stage: 'scaffolded', widget: 'code_completion',
                        question: 'Complete the line.', hints: [] })
    const props = baseProps([bare])
    render(<StepRunner {...(props as any)} />)
    // Silence on the hint button is how a learner ends up clicking "Show full
    // answer": lp-fill ships no hints at all, so the nudge ladder is the offer.
    expect(screen.getByRole('button', { name: /Ask for a nudge \(1 of 2\)/ })).toBeInTheDocument()
  })

  it('an editor rung is edited as code, and stays disabled once it has passed', () => {
    const props = baseProps([step({ id: 'lp-independent', stage: 'independent', widget: 'code',
                                    question: 'Write predict().', starter_code: 'def predict(x, w, b):\n    pass\n' })])
    props.outcome = { passed: true, feedback: 'ok', xp_awarded: 10, evidence: ['independent'],
                      demonstrated: false, lesson_completed: false, next_lesson_id: null, charging: true }
    render(<StepRunner {...(props as any)} />)

    const editor = screen.getByLabelText('Your code') as HTMLTextAreaElement
    expect(editor.value).toContain('def predict')
    expect(editor.disabled).toBe(true)
  })

  it('the session ends on what the learner can now do, and why the next concept exists', () => {
    const props = baseProps([step({ id: 'lp-transfer', stage: 'transfer', widget: 'code' })])
    props.finished = true
    props.step = null
    props.session = {
      ...session([step({ id: 'lp-transfer' })]),
      evidence: ['independent', 'debugged', 'transferred'],
      demonstrated: true,
    }
    props.outcome = { passed: true, feedback: 'ok', xp_awarded: 15, evidence: ['independent'],
                      demonstrated: true, lesson_completed: true, next_lesson_id: 'linreg-mse',
                      charging: true }
    render(<StepRunner {...(props as any)} />)

    expect(screen.getByText(/Linear prediction — demonstrated/)).toBeInTheDocument()
    expect(screen.getByText('✓ Wrote the function yourself')).toBeInTheDocument()
    expect(screen.getByText('✓ Used it on a problem you had not seen')).toBeInTheDocument()
    expect(screen.getByText(/Predictions can be wrong/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Next: Linreg mse/ })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Next: Linreg mse/ }))
    expect(props.onNextLesson).toHaveBeenCalledWith('linreg-mse')
  })

  it('progress counts steps the generator actually planned, including bonus practice', () => {
    const steps = [step({ id: 'a', cleared: true }), step({ id: 'b' }), step({ id: 'c', stage: 'review', bonus: true })]
    const props = baseProps(steps, { progress: { done: 1, total: 2, bonus: 1 } })
    render(<StepRunner {...(props as any)} />)
    expect(screen.getByText('2 / 2')).toBeInTheDocument()
    expect(screen.getByText('+1 practice')).toBeInTheDocument()
  })

  it('shows the rung it is on, in words a learner recognises', () => {
    const props = baseProps([step({ id: 'lp-worked', stage: 'show', widget: 'present',
                                    content: { lead: 'Watch the order of operations.', lines: ['p = 2 * 3 + 1', 'p = 7'], takeaway: 'Multiply first.' } })])
    render(<StepRunner {...(props as any)} />)
    expect(screen.getByText('Worked example')).toBeInTheDocument()
    expect(screen.getByText('Multiply first.')).toBeInTheDocument()
    expect(screen.getByText('ladder: introduce rung for linear-prediction')).toBeInTheDocument()
  })

  it('a review segment reads as practice, not as a new lesson', () => {
    const props = baseProps([step({ id: 'lp-recall', stage: 'review', widget: 'output_prediction',
                                    bonus: true, question: 'What does this print?' })])
    render(<StepRunner {...(props as any)} />)
    expect(screen.getByText('Recall')).toBeInTheDocument()
  })

  it('leaving the ladder goes back, not forwards', () => {
    const props = baseProps([step({ id: 'lp-transfer', stage: 'transfer', widget: 'code' })])
    props.finished = true
    props.step = null
    render(<StepRunner {...(props as any)} />)
    act(() => { fireEvent.click(screen.getByRole('button', { name: /Back to my path/ })) })
    expect(props.onExit).toHaveBeenCalledTimes(1)
  })
})
