/**
 * The client half of a teaching session: fetch the generated ladder, walk it,
 * post each rung, and hold exactly enough state to render one card at a time.
 *
 * Deliberately self-contained rather than woven into the learning session hook.
 * A lesson either has authored teaching steps and runs through here, or it runs
 * through the existing exercise flow untouched — and the overwhelming majority of
 * the curriculum is still the second case, so the ladder must not be able to
 * disturb it.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import type { HeartStatus } from '../api'

export type LadderStep = {
  id: string
  stage: string
  widget: string
  concept: string
  stakes: 'free' | 'charged'
  bonus: boolean
  reason: string
  title?: string
  question?: string
  options?: string[]
  pairs?: { left: string; right: string }[]
  blanks?: string[]
  correct_order?: string[]
  starter_code?: string
  content?: Record<string, any>
  action?: string
  hints?: string[]
  cleared: boolean
}

export type LadderSession = {
  lesson_id: string
  skill: string
  concept: string
  objective: string
  story: { why_this?: string; why_next?: string }
  planned_steps: number
  bonus_steps: number
  steps: LadderStep[]
  trace: string[]
  demonstrated: boolean
  evidence: string[]
}

export type StepOutcome = {
  passed: boolean
  feedback: string
  explanation?: string | null
  xp_awarded: number
  evidence: string[]
  demonstrated: boolean
  lesson_completed: boolean
  next_lesson_id: string | null
  charging: boolean
  hearts?: HeartStatus
  session?: LadderSession
  misconception?: string | null
}

export type LadderMode = 'loading' | 'ladder' | 'legacy' | 'error'

/** Shape check, not a cast: the ladder only takes over a real session. */
export function isLadderSession(value: unknown): value is LadderSession {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Partial<LadderSession>
  return (
    typeof candidate.lesson_id === 'string'
    && Array.isArray(candidate.steps)
    && candidate.steps.length > 0
    && candidate.steps.every((s) => s && typeof s.id === 'string' && typeof s.stage === 'string')
    && typeof candidate.planned_steps === 'number'
  )
}

export function useStepSession(lessonId: string | null) {
  const [mode, setMode] = useState<LadderMode>('loading')
  const [session, setSession] = useState<LadderSession | null>(null)
  const [index, setIndex] = useState(0)
  const [input, setInput] = useState<Record<string, any>>({})
  const [outcome, setOutcome] = useState<StepOutcome | null>(null)
  const [busy, setBusy] = useState(false)
  const [hintsUsed, setHintsUsed] = useState(0)
  const requestedFor = useRef<string | null>(null)

  useEffect(() => {
    if (!lessonId) {
      setMode('loading')
      return
    }
    if (requestedFor.current === lessonId) return
    requestedFor.current = lessonId
    let cancelled = false
    setMode('loading')
    fetch(`/api/lessons/${encodeURIComponent(lessonId)}/session`)
      .then(async (res) => {
        if (cancelled) return
        // 404 with no_step_pool is the normal case for a lesson that has not
        // been written as a ladder yet: it is not an error the learner sees.
        if (res.status === 404) {
          setMode('legacy')
          return
        }
        if (!res.ok) {
          setMode('error')
          return
        }
        const body = (await res.json()) as LadderSession | null
        // Only a structurally complete session takes the lesson over. A proxy
        // error page, an older server that answers 200 with `{}`, or a truncated
        // body must fall through to the ordinary lesson flow rather than render
        // an empty ladder in place of work the learner can actually do.
        if (!isLadderSession(body)) {
          setMode('legacy')
          return
        }
        setSession(body)
        setIndex(firstUncleared(body))
        setOutcome(null)
        setInput({})
        setHintsUsed(0)
        setMode('ladder')
      })
      .catch(() => {
        if (!cancelled) setMode('error')
      })
    return () => {
      cancelled = true
    }
  }, [lessonId])

  const step = session?.steps[index] ?? null

  const advance = useCallback(() => {
    setOutcome(null)
    setHintsUsed(0)
    setInput({})
    setIndex((i) => {
      if (!session) return i
      const next = session.steps.slice(i + 1).findIndex((s) => !s.cleared)
      return next === -1 ? session.steps.length : i + 1 + next
    })
  }, [session])

  /** Rung the learner stands on now, after the server's next session if there is one. */
  const applySession = useCallback((next?: LadderSession) => {
    if (!next) return
    setSession(next)
    setIndex(firstUncleared(next))
  }, [])

  const markSeen = useCallback(async () => {
    if (!session || !step) return
    setBusy(true)
    try {
      const res = await fetch(
        `/api/lessons/${encodeURIComponent(session.lesson_id)}/steps/${encodeURIComponent(step.id)}/seen`,
        { method: 'POST' },
      )
      if (res.ok) {
        const next = cloneSessionWithout(session, step.id)
        applySession(next)
      }
    } finally {
      setBusy(false)
    }
  }, [session, step, applySession])

  const attempt = useCallback(async () => {
    if (!session || !step) return null
    setBusy(true)
    try {
      const payload = payloadFor(step, input[step.id] || {})
      const res = await fetch(
        `/api/lessons/${encodeURIComponent(session.lesson_id)}/steps/${encodeURIComponent(step.id)}/attempt`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ payload, hints_used: hintsUsed }),
        },
      )
      const body = await res.json().catch(() => null)
      if (!res.ok) {
        if (res.status === 403 && body?.detail?.hearts) {
          setOutcome({
            passed: false,
            feedback: body?.detail?.message || 'Out of hearts.',
            xp_awarded: 0,
            evidence: session.evidence,
            demonstrated: false,
            lesson_completed: false,
            next_lesson_id: null,
            charging: true,
            hearts: body.detail.hearts,
          })
          void api.hearts().then((status) => status && setOutcome((o) => (o ? { ...o, hearts: status } : o)))
        }
        return null
      }
      const outcome = body as StepOutcome
      setOutcome(outcome)
      if (outcome.hearts) void api.hearts().then((status) => status && setOutcome((o) => (o ? { ...o, hearts: status } : o)))
      if (outcome.passed) {
        applySession(outcome.session)
      }
      return outcome
    } finally {
      setBusy(false)
    }
  }, [session, step, input, hintsUsed, applySession])

  const progress = useMemo(() => {
    if (!session) return { done: 0, total: 0, bonus: 0 }
    return {
      done: session.steps.filter((s) => s.cleared).length,
      total: session.planned_steps,
      bonus: session.bonus_steps,
    }
  }, [session])

  return {
    mode,
    session,
    step,
    index,
    input: step ? input[step.id] || {} : {},
    setInput: (patch: Record<string, any>) =>
      setInput((prev) => ({ ...prev, [step?.id ?? '_']: { ...(prev[step?.id ?? '_'] || {}), ...patch } })),
    outcome,
    clearOutcome: () => setOutcome(null),
    busy,
    hintsUsed,
    bumpHints: () => setHintsUsed((n) => n + 1),
    advance,
    markSeen,
    attempt,
    progress,
    finished: Boolean(session) && index >= (session?.steps.length ?? 0),
  }
}

/** Start at the first rung the learner has not already been through. */
function firstUncleared(session: LadderSession): number {
  const i = session.steps.findIndex((s) => !s.cleared)
  return i === -1 ? session.steps.length : i
}

/**
 * The session, with one rung marked resolved — built locally rather than waiting
 * for a refetch, so continuing never flashes the rung just finished. The caller
 * then re-derives the position from the first uncleared rung, which keeps a
 * review segment queued past the end from being pulled forward.
 */
function cloneSessionWithout(session: LadderSession, stepId: string): LadderSession {
  const steps = session.steps.map((s) => (s.id === stepId ? { ...s, cleared: true } : s))
  return { ...session, steps }
}

function payloadFor(step: LadderStep, state: Record<string, any>): Record<string, any> {
  switch (step.widget) {
    case 'ordering':
      return { order: state.order || state.answers || [] }
    case 'matching':
      return { pairs: state.pairs || [] }
    case 'select_multiple':
      return { answers: state.answers || state.selected || [] }
    case 'fill_blank':
    case 'code_completion':
      return { answers: state.answers || [], code: state.code }
    case 'code':
    case 'tiny_coding':
    case 'identify_mistake':
      return { code: state.code ?? '' }
    default:
      return { answer: state.answer ?? '' }
  }
}
