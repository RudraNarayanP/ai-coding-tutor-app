/**
 * The hook that decides whether a lesson runs as a ladder.
 *
 * This file exists because of a defect the component tests could not see: the
 * session hook had a "already fetched for this lesson id" guard, and StrictMode
 * (which `main.tsx` really uses, and no test did) mounts every effect twice. The
 * second mount skipped the fetch, the mode stayed `loading`, and every ladder
 * lesson silently fell back to the legacy workspace in the browser while the
 * suite stayed green. So: mount under StrictMode here, or this bug comes back.
 */

import { StrictMode } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { isLadderSession, useStepSession } from './useStepSession'

const STEP = {
  id: 'lp-intro',
  stage: 'introduce',
  widget: 'present',
  concept: 'linear-prediction',
  stakes: 'free',
  bonus: false,
  reason: 'ladder: introduce rung for linear-prediction',
  content: { lead: 'A prediction is one number pushed through one formula.' },
  cleared: false,
}

const SESSION = {
  lesson_id: 'linreg-predict',
  skill: 'linear-prediction',
  concept: 'linear-prediction',
  objective: 'Write predict(x, w, b)',
  story: { why_this: 'Everything a model knows is this formula.', why_next: 'Then measure it.' },
  planned_steps: 1,
  bonus_steps: 0,
  steps: [STEP],
  trace: ['introduce lp-intro ladder'],
  demonstrated: false,
  evidence: [],
}

function Probe({ lessonId }: { lessonId: string | null }) {
  const session = useStepSession(lessonId)
  return <div data-testid="probe">{`${session.mode}:${session.session?.steps.length ?? 0}`}</div>
}

/** The same hook with its two verbs on screen, so a test can stand in a tap. */
function InteractiveProbe() {
  const ladder = useStepSession('linreg-predict')
  return (
    <div>
      <span data-testid="current">{ladder.step?.id ?? 'none'}</span>
      <span data-testid="outcome">{ladder.outcome ? String(ladder.outcome.passed) : 'none'}</span>
      <button type="button" onClick={() => void ladder.attempt()}>answer</button>
      <button type="button" onClick={ladder.advance}>continue</button>
    </div>
  )
}

function respond(body: unknown, status = 200) {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: status < 400,
    status,
    json: async () => body,
  })))
}

function respondWith(handler: (url: string) => { body: unknown, status?: number }) {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const { body, status = 200 } = handler(String(input))
    return { ok: status < 400, status, json: async () => body }
  }))
}

beforeEach(() => {
  vi.unstubAllGlobals()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useStepSession', () => {
  it('takes the lesson over when the session is a real ladder', async () => {
    respond(SESSION)
    render(<Probe lessonId="linreg-predict" />)
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('ladder:1'))
  })

  it('still takes it over under StrictMode, where every effect runs twice', async () => {
    respond(SESSION)
    render(
      <StrictMode>
        <Probe lessonId="linreg-predict" />
      </StrictMode>,
    )
    // The old guard left this at "loading:0", which LessonScreen reads as
    // "not a ladder" and answers by showing the raw task instead of teaching it.
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('ladder:1'))
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(2)
  })

  it('leaves a lesson alone when the server has no pool for it', async () => {
    respond({ detail: { error: 'no_step_pool' } }, 404)
    render(
      <StrictMode>
        <Probe lessonId="variables-step-1" />
      </StrictMode>,
    )
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('legacy:0'))
  })

  it('refuses to hijack a lesson on a 200 that is not a session', async () => {
    respond({})
    render(<Probe lessonId="linreg-predict" />)
    // Structural check first, cast never.
    expect(isLadderSession({})).toBe(false)
    expect(isLadderSession({ ...SESSION, steps: [{ id: 'x' }] })).toBe(false)
    expect(isLadderSession(SESSION)).toBe(true)
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('legacy:0'))
  })

  it('holds a passed rung on screen until the learner continues', async () => {
    const ask = (id: string) => ({ ...STEP, id, stage: 'interact', widget: 'mcq', cleared: false })
    const both = { ...SESSION, steps: [ask('ask-1'), ask('ask-2')], planned_steps: 2 }
    const after = { ...SESSION, steps: [ask('ask-2')], planned_steps: 1 }
    respondWith((url) => (url.includes('/attempt')
      ? { body: { ...PASSED_OUTCOME, passed: true, session: after } }
      : { body: both }))
    render(<InteractiveProbe />)
    await screen.findByText('answer')

    fireEvent.click(screen.getByText('answer'))
    // The success panel belongs to ask-1, so ask-1 stays on screen: applying the
    // returned session at grading time put "Continue" on an unanswered ask-2 and
    // one tap quietly skipped a rung the server had never marked.
    await waitFor(() => expect(screen.getByTestId('outcome')).toHaveTextContent('true'))
    expect(screen.getByTestId('current')).toHaveTextContent('ask-1')

    fireEvent.click(screen.getByText('continue'))
    await waitFor(() => expect(screen.getByTestId('current')).toHaveTextContent('ask-2'))
    expect(screen.getByTestId('outcome')).toHaveTextContent('none')
  })

  it('hands a stuck learner to the hint ladder the authored steps did not cover', async () => {
    const asked: any[] = []
    const oneHint = { ...STEP, id: 'ask-1', stage: 'independent', widget: 'code',
                      hints: ['Which name gets scaled?'] }
    respondWith((url) => {
      if (url.includes('/api/tutor')) {
        asked.push(JSON.parse(lastTutorBody()))
        return { body: { message: 'Write the expression that scales x first.', source: 'ai' } }
      }
      return { body: { ...SESSION, steps: [oneHint], planned_steps: 1 } }
    })
    render(<HintProbe />)
    await screen.findByText('hint')

    fireEvent.click(screen.getByText('hint'))
    // The authored rung goes first and costs no request.
    expect(screen.getByTestId('hints')).toHaveTextContent('Which name gets scaled?')
    expect(asked).toHaveLength(0)

    fireEvent.click(screen.getByText('hint'))
    await waitFor(() => expect(screen.getByTestId('hints')).toHaveTextContent('scales x first'))
    expect(asked).toHaveLength(1)
    expect(asked[0].hint_level).toBe(2)
    expect(asked[0].previous_hints).toEqual(['Which name gets scaled?'])
    expect(asked[0].lesson_id).toBe('linreg-predict')
  })
  it('counts progress against the whole ladder, not the part still owed', async () => {
    const rung = (id: string) => ({ ...STEP, id, stage: 'interact', widget: 'mcq', cleared: false })
    const three = { ...SESSION, steps: [rung('a'), rung('b'), rung('c')], planned_steps: 3, ladder_steps: 3 }
    const twoLeft = { ...SESSION, steps: [rung('b'), rung('c')], planned_steps: 2, ladder_steps: 3 }
    respondWith((url) => (url.includes('/attempt')
      ? { body: { ...PASSED_OUTCOME, passed: true, session: twoLeft } }
      : { body: three }))
    render(<ProgressProbe />)
    await screen.findByText('answer')
    expect(screen.getByTestId('progress')).toHaveTextContent('0/3')

    fireEvent.click(screen.getByText('answer'))
    await waitFor(() => expect(screen.getByTestId('outcome')).toHaveTextContent('true'))
    fireEvent.click(screen.getByText('continue'))
    // The generator only returns what is still owed, so a bar built from the
    // session length alone would drop back to "1 / 2" after one success.
    await waitFor(() => expect(screen.getByTestId('progress')).toHaveTextContent('1/3'))
  })

  it('lets a finished lesson celebrate instead of opening its next check', async () => {
    const rung = (id: string) => ({ ...STEP, id, stage: 'transfer', widget: 'code', cleared: false })
    const last = { ...SESSION, steps: [rung('lp-transfer')], planned_steps: 1, ladder_steps: 8 }
    // Passing the transfer demonstrates the concept, so the generator fades the
    // lesson into its mixed-skill check — which must wait for the next visit.
    const faded = { ...SESSION, steps: [rung('lp-mixed-check')], planned_steps: 1, ladder_steps: 8 }
    respondWith((url) => (url.includes('/attempt')
      ? { body: { ...PASSED_OUTCOME, passed: true, lesson_completed: true, next_lesson_id: 'linreg-mse', session: faded } }
      : { body: last }))
    render(<FinishedProbe />)
    await screen.findByText('answer')

    fireEvent.click(screen.getByText('answer'))
    await waitFor(() => expect(screen.getByTestId('outcome')).toHaveTextContent('true'))
    expect(screen.getByTestId('finished')).toHaveTextContent('false')

    fireEvent.click(screen.getByText('continue'))
    await waitFor(() => expect(screen.getByTestId('finished')).toHaveTextContent('true'))
    // The summary reads the outcome it just earned, so Continue must not clear it.
    expect(screen.getByTestId('outcome')).toHaveTextContent('true')
  })
})

function FinishedProbe() {
  const ladder = useStepSession('linreg-predict')
  return (
    <div>
      <span data-testid="finished">{String(ladder.finished)}</span>
      <span data-testid="outcome">{ladder.outcome ? String(ladder.outcome.passed) : 'none'}</span>
      <button type="button" onClick={() => void ladder.attempt()}>answer</button>
      <button type="button" onClick={ladder.advance}>continue</button>
    </div>
  )
}

function ProgressProbe() {
  const ladder = useStepSession('linreg-predict')
  return (
    <div>
      <span data-testid="progress">{`${ladder.progress.done}/${ladder.progress.total}`}</span>
      <span data-testid="outcome">{ladder.outcome ? String(ladder.outcome.passed) : 'none'}</span>
      <button type="button" onClick={() => void ladder.attempt()}>answer</button>
      <button type="button" onClick={ladder.advance}>continue</button>
    </div>
  )
}

const PASSED_OUTCOME = {
  feedback: 'Correct',
  xp_awarded: 10,
  evidence: [],
  demonstrated: false,
  lesson_completed: false,
  next_lesson_id: null,
  charging: false,
}

/** Reads the body of the stubbed fetch, the way the server would see it. */
function lastTutorBody(): string {
  const calls = (fetch as any).mock.calls
  const withBody = calls.filter((call: any[]) => String(call[0]).includes('/api/tutor'))
  return String(withBody[withBody.length - 1][1]?.body ?? '{}')
}

function HintProbe() {
  const ladder = useStepSession('linreg-predict')
  return (
    <div>
      <span data-testid="hints">
        {[...(ladder.step?.hints ?? []).slice(0, ladder.hintsUsed), ...ladder.extraHints].join(' / ')}
      </span>
      <button type="button" onClick={() => void ladder.bumpHints()}>hint</button>
    </div>
  )
}
