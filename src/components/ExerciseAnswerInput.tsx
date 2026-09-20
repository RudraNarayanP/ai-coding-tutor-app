import React, { useMemo } from 'react'
import {
  CHOICE_TYPES,
  CODE_TYPES,
  FILL_TYPES,
  MCQ_TYPES,
  isCodeLikeExercise,
  isKnownExerciseType,
  widgetFor,
} from '../utils/exerciseTypes'

// The type lists live in src/utils/exerciseTypes.ts, which mirrors
// backend/exercise_types.py. Re-exported here so existing import sites keep
// working while there remains exactly one definition.
export { CHOICE_TYPES, CODE_TYPES, FILL_TYPES, MCQ_TYPES, isCodeLikeExercise, widgetFor }

function shuffled<T>(items: T[]): T[] {
  const arr = [...items]
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[arr[i], arr[j]] = [arr[j], arr[i]]
  }
  return arr
}

function hashString(text: string): number {
  let h = 2166136261
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

/**
 * A stable, per-exercise option order.
 *
 * Curriculum authors keep writing `options` with the correct choice first, and
 * the server ships that array untouched — so "always tap the first button"
 * answers every multiple-choice question. Reordering by a hash of the exercise
 * id breaks that shortcut while keeping the order identical between renders
 * and sessions, so the buttons never jump around under the learner.
 */
export function orderedOptions(exerciseId: string, options: string[]): string[] {
  if (options.length < 3) return options
  const seed = hashString(String(exerciseId || ''))
  return options
    .map((option, index) => ({ option, key: hashString(`${seed}:${index}:${option}`) }))
    .sort((a, b) => a.key - b.key)
    .map((entry) => entry.option)
}

interface ExerciseAnswerInputProps {
  exercise: any
  exType: string
  exState: Record<string, any>
  disabled: boolean
  setState: (patch: Record<string, any>) => void
}

// Non-code exercise inputs (MCQ, select-multiple, ordering, matching, generic),
// shared by the inline ExercisePanel and the fullscreen ExerciseWorkspace so
// every course renders the same widgets.
export const ExerciseAnswerInput: React.FC<ExerciseAnswerInputProps> = ({
  exercise,
  exType,
  exState,
  disabled,
  setState,
}) => {
  const opts = exercise.options || []
  const fallbackOptions = exType === 'true_false' ? ['True', 'False'] : []
  const displayOptions: string[] = useMemo(
    () => orderedOptions(exercise.id, opts.length > 0 ? opts : fallbackOptions),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [exercise.id, exType, opts.join('|')],
  )

  const shuffledRights: string[] = useMemo(() => {
    const pairs: Array<{ left: string; right: string }> = exercise.pairs || []
    return shuffled<string>(pairs.map((p) => p.right))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exercise.id])

  if (MCQ_TYPES.includes(exType)) {
    return (
      <div className="exercise-options-grid">
        {displayOptions.map((opt: string) => (
          <button key={opt}
            className={`exercise-option-btn ${exState.answer === opt ? 'selected' : ''}`}
            disabled={disabled}
            onClick={() => setState({ answer: opt })}
          >{opt}</button>
        ))}
      </div>
    )
  }

  if (exType === 'select_multiple') {
    return (
      <div className="exercise-options-grid">
        {displayOptions.map((opt: string) => {
          const s = new Set<string>(exState.answers || []); const sel = s.has(opt)
          return (
            <button key={opt} className={`exercise-option-btn ${sel ? 'selected' : ''}`}
              onClick={() => {
                const n = new Set(s)
                if (sel) n.delete(opt); else n.add(opt)
                setState({ answers: Array.from(n) })
              }}
              disabled={disabled}
            >{sel ? '☑ ' : '☐ '}{opt}</button>
          )
        })}
      </div>
    )
  }

  if (exType === 'ordering') {
    const orderVal: string[] = exState.order || []
    const remaining = [...opts]
    orderVal.forEach((picked) => {
      const idx = remaining.indexOf(picked)
      if (idx >= 0) remaining.splice(idx, 1)
    })
    return (
      <div className="exercise-ordering">
        <div className="exercise-ordering-sequence" aria-label="Your sequence">
          {orderVal.length === 0 && (
            <span className="exercise-ordering-empty">Tap the blocks below in the correct order…</span>
          )}
          {orderVal.map((item, idx) => (
            <button
              key={`${item}-${idx}`}
              type="button"
              className="exercise-chip exercise-chip-placed"
              disabled={disabled}
              onClick={() => setState({ order: orderVal.filter((_, i) => i !== idx) })}
              aria-label={`Remove ${item} from sequence`}
            >
              {idx + 1}. {item} ✕
            </button>
          ))}
        </div>
        <div className="exercise-chip-pool">
          {remaining.map((opt: string, idx: number) => (
            <button
              key={`${opt}-${idx}`}
              type="button"
              className="exercise-chip"
              disabled={disabled}
              onClick={() => setState({ order: [...orderVal, opt] })}
            >
              {opt}
            </button>
          ))}
        </div>
        {orderVal.length > 0 && (
          <button
            type="button"
            className="duo-button duo-button-secondary exercise-code-reset"
            disabled={disabled}
            onClick={() => setState({ order: [] })}
          >
            Clear
          </button>
        )}
      </div>
    )
  }

  if (exType === 'matching') {
    const pairs = exercise.pairs || []
    const lefts: string[] = pairs.map((p: any) => p.left)
    const matched: Array<{ left: string; right: string }> = exState.pairs || []
    const selectedLeft: string | null = exState.selectedLeft ?? null
    const matchedLefts = new Set(matched.map((p) => p.left))
    const matchedRights = new Set(matched.map((p) => p.right))

    const pickLeft = (left: string) => {
      if (matchedLefts.has(left)) {
        setState({ pairs: matched.filter((p) => p.left !== left) })
        return
      }
      setState({ selectedLeft: selectedLeft === left ? null : left })
    }
    const pickRight = (right: string) => {
      if (!selectedLeft) return
      const next = matched.filter((p) => p.left !== selectedLeft && p.right !== right)
      next.push({ left: selectedLeft, right })
      setState({ pairs: next, selectedLeft: null })
    }

    return (
      <div className="exercise-matching">
        <div className="exercise-matching-cols">
          <div className="exercise-matching-col">
            {lefts.map((left: string, idx: number) => (
              <button
                key={`${left}-${idx}`}
                type="button"
                className={`exercise-chip ${matchedLefts.has(left) ? 'exercise-chip-placed' : ''} ${selectedLeft === left ? 'exercise-chip-active' : ''}`}
                disabled={disabled}
                onClick={() => pickLeft(left)}
              >
                {left}
              </button>
            ))}
          </div>
          <div className="exercise-matching-col">
            {shuffledRights.map((right: string, idx: number) => (
              <button
                key={`${right}-${idx}`}
                type="button"
                className={`exercise-chip ${matchedRights.has(right) ? 'exercise-chip-placed' : ''}`}
                disabled={disabled || !selectedLeft}
                onClick={() => pickRight(right)}
              >
                {right}
              </button>
            ))}
          </div>
        </div>
        <p className="duo-empty-note">
          {matched.length === 0
            ? 'Tap an item on the left, then its match on the right.'
            : `${matched.length} of ${lefts.length} paired — tap a paired left item to unpair it.`}
        </p>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      <label style={{ fontWeight: 700, fontSize: '14px' }} htmlFor={`generic-input-${exercise.id}`}>
        Your answer:
      </label>
      <input
        id={`generic-input-${exercise.id}`}
        type="text"
        value={exState.answer || ''}
        placeholder="Type your answer here…"
        disabled={disabled}
        onChange={(e) => setState({ answer: e.target.value })}
        style={{ padding: '10px 14px', borderRadius: '10px', border: '2px solid var(--line)', fontWeight: 700, fontSize: '15px', background: 'var(--input-bg)', color: 'var(--ink)' }}
      />
    </div>
  )
}

export default ExerciseAnswerInput
