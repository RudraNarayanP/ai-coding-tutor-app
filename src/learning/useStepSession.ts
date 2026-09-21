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
  /** Every rung of this concept, cleared or not — the honest denominator. */
  ladder_steps?: number
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

/** How many AI nudges one rung may hand out, so a hint is never a bottomless pit. */
const EXTRA_HINTS_PER_STEP = 2

/** A hint that arrives when the authored ladder has nothing left for this rung. */
export type HintSource = 'authored' | 'ai' | 'offline'

/** A hint that does not need a provider: the same move the tutor would ask for. */
const OFFLINE_NUDGE =
  'Read the question again and name, out loud or in a comment, the one value it asks ' +
  'for. Then change only the line that produces that value.'

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
  const [extraHints, setExtraHints] = useState<string[]>([])
  const [hintBusy, setHintBusy] = useState(false)

  useEffect(() => {
    if (!lessonId) {
      setMode('loading')
      return
    }
    // No "already requested for this lesson" guard here, on purpose. The effect
    // only re-runs when lessonId changes, and in development StrictMode React
    // mounts, cleans up and mounts again — a guard keyed on the id made the
    // second mount skip the fetch, so the mode stayed 'loading' and every ladder
    // lesson silently fell back to the legacy workspace in the browser while all
    // tests (which do not use StrictMode) passed. The `cancelled` flag below is
    // what makes the double mount harmless: the abandoned run cannot write.
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
        setExtraHints([])
        setCelebrate(false)
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

  /**
   * The session the server returned after a pass, held until the learner leaves
   * the card they just answered.
   *
   * Applying it immediately moved the index while the success panel was still
   * showing, so the *next* card rendered with "Continue →" as if it had been
   * answered — one tap and a rung was skipped that the server never marked. A
   * passed step now keeps its own panel until the tap, and the walk forward
   * happens here.
   */
  const pending = useRef<LadderSession | null>(null)

  /** Set when a pass completed the lesson, so Continue lands on the summary. */
  const [celebrate, setCelebrate] = useState(false)

  const advance = useCallback(() => {
    if (outcome?.lesson_completed) {
      // The celebration is the reward for the last rung, so it must not be
      // stolen by whatever the generator queued next. Demonstrating the concept
      // also fades the lesson into its mixed-skill check, which used to appear
      // immediately after the learner had finished — an exit ticket where the
      // summary of what they learned should be. The check is still there on the
      // next visit. The outcome stays on screen because the summary reports its
      // XP and its next-lesson id.
      setCelebrate(true)
      return
    }
    setOutcome(null)
    setHintsUsed(0)
    setExtraHints([])
    setInput({})
    const next = pending.current
    pending.current = null
    if (next) {
      setSession(next)
      setIndex(firstUncleared(next))
      return
    }
    setIndex((i) => {
      if (!session) return i
      const ahead = session.steps.slice(i + 1).findIndex((s) => !s.cleared)
      return ahead === -1 ? session.steps.length : i + 1 + ahead
    })
  }, [session, outcome])

  /** Rung the learner stands on now, after the server's next session if there is one. */
  const applySession = useCallback((next?: LadderSession) => {
    if (!next) return
    setSession(next)
    setIndex(firstUncleared(next))
    setHintsUsed(0)
    setExtraHints([])
    setCelebrate(false)
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
        pending.current = outcome.session ?? null
      }
      return outcome
    } finally {
      setBusy(false)
    }
  }, [session, step, input, hintsUsed])

  /**
   * One more rung of the hint ladder, authored first and generated after.
   *
   * Only the rungs where a learner can genuinely stall carry authored hints, and
   * a ladder that stops at two leaves the third request with nothing — which is
   * how a learner ends up staring at a screen or clicking "Show full answer".
   * So the authored hints go first, in their designed order, and when they run
   * out the existing tutor ladder takes over at the level the learner has
   * reached (conceptual → procedural → structural → near-solution). It never
   * volunteers the solution, and if the provider is down the learner still gets
   * a usable nudge rather than an error.
   */
  const bumpHints = useCallback(async () => {
    if (!session || !step) return
    const authored = step.hints ?? []
    if (hintsUsed < authored.length) {
      setHintsUsed((n) => n + 1)
      return
    }
    if (extraHints.length >= EXTRA_HINTS_PER_STEP) return
    const revealed = [...authored.slice(0, hintsUsed), ...extraHints]
    setHintBusy(true)
    try {
      const res = await api.tutor({
        lesson_id: session.lesson_id,
        lesson_title: session.objective || session.skill,
        unit_title: '',
        concept_title: session.concept,
        prerequisites: [],
        instructions: (step.question || session.objective || '').slice(0, 2000),
        code: input[step.id]?.code ?? step.starter_code ?? '',
        test_results: outcome && !outcome.passed
          ? [{ name: step.id, passed: false, required: true, description: outcome.feedback, error: outcome.feedback }]
          : [],
        previous_hints: revealed,
        hint_level: Math.min(4, revealed.length + 1),
        session_id: 'default',
        user_id: 'default_user',
      })
      const data = await res.json().catch(() => null)
      const message = res.ok && data?.message && data?.available !== false
        ? String(data.message)
        : OFFLINE_NUDGE
      setExtraHints((list) => [...list, message])
    } catch {
      // A hint that fails to arrive is the one thing this path must not do.
      setExtraHints((list) => [...list, OFFLINE_NUDGE])
    } finally {
      setHintBusy(false)
    }
  }, [session, step, hintsUsed, extraHints, input, outcome])

  const progress = useMemo(() => {
    if (!session) return { done: 0, total: 0, bonus: 0 }
    // The denominator is the whole ladder, not the part of it still owed: the
    // generator drops cleared rungs from the session, so counting only what came
    // back made the bar restart ("3 / 8" then "1 / 5") every time a rung was
    // answered — the opposite of the "one more lesson" pull it is supposed to be.
    const owed = session.steps.filter((s) => !s.cleared && !s.bonus).length
    const total = session.ladder_steps || session.planned_steps || session.steps.length
    if (total === 0) return { done: 0, total: session.steps.length, bonus: 0 }
    return {
      done: Math.min(total, Math.max(0, total - owed)),
      total,
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
    bumpHints,
    extraHints,
    hintBusy,
    advance,
    markSeen,
    attempt,
    progress,
    finished: Boolean(session)
      && (celebrate || index >= (session?.steps.length ?? 0)),
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
