import React, { useMemo, useState } from 'react'
import { ExerciseFeedback } from './ExerciseFeedback'

interface Props {
  exercise: any
  exerciseInput: Record<string, any>
  exercisePhase: string
  exerciseFeedback: any
  exercisePosition: number
  exerciseTotal: number
  completedExerciseCount: number
  onInputChange: any
  onSubmit: () => void
  onContinue: () => void
  onRetry: () => void
  onRunCode?: () => void
  isRunningCode?: boolean
  codeTestsPassed?: boolean
  lessonId?: string | null
}

const MCQ_TYPES = ['mcq', 'true_false', 'output_prediction', 'debugging', 'identify_error']
const FILL_TYPES = ['fill_blank', 'code_completion']
const CODE_TYPES = ['code', 'tiny_coding', 'identify_mistake']

function usesInlineCodeEditor(exercise: { type?: string; starter_code?: string; code?: string }) {
  const exType = (exercise.type || 'code').toLowerCase().trim()
  return FILL_TYPES.includes(exType) && !!(exercise.starter_code || exercise.code)
}

function shuffled<T>(items: T[]): T[] {
  const arr = [...items]
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[arr[i], arr[j]] = [arr[j], arr[i]]
  }
  return arr
}

const ExercisePanel: React.FC<Props> = (props) => {
  const {exercise, exerciseInput, exercisePhase, exerciseFeedback, exercisePosition, exerciseTotal, completedExerciseCount, onInputChange, onSubmit, onContinue, onRetry, codeTestsPassed, lessonId} = props
  const [showDeepDive, setShowDeepDive] = useState(false)
  const exType = (exercise.type || 'code').toLowerCase().trim()
  const opts = exercise.options || []
  const exState = exerciseInput[exercise.id] || {}
  const disabled = exercisePhase === 'checking' || exercisePhase === 'correct'

  const pct = exerciseTotal > 0 ? (completedExerciseCount / exerciseTotal) * 100 : 0

  const shuffledRights: string[] = useMemo(() => {
    const pairs: Array<{ left: string; right: string }> = exercise.pairs || []
    return shuffled<string>(pairs.map((p) => p.right))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exercise.id])

  const setState = (patch: Record<string, any>) => {
    onInputChange((prev: any) => ({ ...prev, [exercise.id]: { ...prev[exercise.id], ...patch } }))
  }

  const renderInfo = () => (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
        <span style={{ fontWeight: 800, fontSize: '14px', color: 'var(--ink-soft)' }}>
          Exercise {exercisePosition} of {exerciseTotal}
        </span>
        <span style={{ fontWeight: 700, fontSize: '13px', color: 'var(--ink-soft)' }}>
          {completedExerciseCount} / {exerciseTotal} complete
        </span>
      </div>
      <div style={{ height: '8px', borderRadius: '4px', background: 'var(--line)', overflow: 'hidden', marginBottom: '16px' }}
        role="progressbar" aria-label="Lesson progress"
        aria-valuenow={completedExerciseCount} aria-valuemin={0} aria-valuemax={exerciseTotal}>
        <div style={{ height: '100%', width: `${pct}%`, background: 'var(--green)', transition: 'width 0.3s' }} />
      </div>
    </div>
  )

  const renderMicroInstruction = () => {
    const microExp = exercise.micro_explanation || exercise.description || ''
    const workedExample = exercise.worked_example || ''
    const takeaway = exercise.worked_example_takeaway || ''

    if (!microExp && !workedExample) return null

    return (
      <div className="micro-instruction-box" style={{
        backgroundColor: 'var(--surface-sunken, #0f172a)',
        border: '2px solid var(--line, #334155)',
        borderRadius: '12px',
        padding: '16px',
        marginBottom: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px'
      }}>
        {microExp && (
          <p style={{ fontSize: '15px', fontWeight: 600, color: 'var(--ink, #f8fafc)', margin: 0, lineHeight: '1.4' }}>
            💡 {microExp}
          </p>
        )}
        {workedExample && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <div style={{ fontSize: '12px', fontWeight: 800, color: '#38bdf8', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              EXAMPLE:
            </div>
            <pre style={{
              background: '#1e293b',
              color: '#38bdf8',
              padding: '10px 14px',
              borderRadius: '8px',
              fontSize: '13px',
              fontFamily: 'monospace',
              margin: 0,
              overflowX: 'auto'
            }}>
              <code>{workedExample}</code>
            </pre>
            {takeaway && (
              <p style={{ fontSize: '13px', fontWeight: 600, color: 'var(--ink-soft, #94a3b8)', margin: 0 }}>
                {takeaway}
              </p>
            )}
          </div>
        )}
      </div>
    )
  }

  const renderOptionalDeepDive = () => {
    const deepText = exercise.deep_dive || exercise.explanation || ''
    if (!deepText) return null

    return (
      <div style={{ marginTop: '12px' }}>
        <button
          type="button"
          className="duo-button duo-button-secondary"
          style={{ fontSize: '12px', padding: '4px 10px', borderRadius: '6px' }}
          onClick={() => setShowDeepDive(!showDeepDive)}
        >
          {showDeepDive ? 'Hide Deep Dive ▲' : '💡 Why does this work? / Learn More ▼'}
        </button>
        {showDeepDive && (
          <div style={{
            marginTop: '8px',
            padding: '12px',
            borderRadius: '8px',
            background: 'var(--surface-sunken, #0f172a)',
            border: '1px solid var(--line, #334155)',
            fontSize: '13px',
            fontWeight: 500,
            color: 'var(--ink-soft, #cbd5e1)',
            lineHeight: '1.4'
          }}>
            {deepText}
          </div>
        )}
      </div>
    )
  }

  const renderCta = () => {
    if (exercisePhase === 'correct' && exerciseFeedback) {
      return (
        <div className="duo-feedback-panel success duo-great-job" style={{ marginTop: '16px' }}>
          <div className="duo-feedback-title"><span>🎉 Correct!</span></div>
          <p style={{ fontWeight: 700 }}>{exerciseFeedback.feedback}</p>
          {exerciseFeedback.xpAwarded > 0 && (
            <div className="duo-type-badge duo-type-practice" style={{ alignSelf: 'flex-start' }}>
              +{exerciseFeedback.xpAwarded} XP
            </div>
          )}
          <ExerciseFeedback
            key={`fb-${exercise.id}`}
            exerciseId={exercise.id}
            lessonId={lessonId ?? null}
          />
          <button className="duo-button duo-button-primary" style={{ marginTop: '12px', padding: '12px 24px' }} onClick={onContinue}>Continue →</button>
        </div>
      )
    }
    if (exercisePhase === 'incorrect' && exerciseFeedback) {
      return (
        <div className="duo-feedback-panel error" style={{ marginTop: '16px' }}>
          <div className="duo-feedback-title"><span>&#10007; Not quite</span></div>
          <p style={{ fontWeight: 700 }}>{exerciseFeedback.feedback}</p>
          {exerciseFeedback.explanation && (
            <p style={{ fontWeight: 600, fontSize: '14px', opacity: 0.9 }}>{exerciseFeedback.explanation}</p>
          )}
          <ExerciseFeedback
            key={`fb-${exercise.id}`}
            exerciseId={exercise.id}
            lessonId={lessonId ?? null}
            reportOnly
          />
          <button className="duo-button duo-button-primary" style={{ marginTop: '12px', padding: '12px 24px' }} onClick={onRetry}>Try Again</button>
        </div>
      )
    }
    const isCodeExercise = CODE_TYPES.includes(exType) || usesInlineCodeEditor(exercise)
    const continueLabel = isCodeExercise && codeTestsPassed ? 'Continue →' : 'Check Answer'

    return (
      <button className="duo-button duo-button-primary" style={{ marginTop: '16px', padding: '12px 24px' }}
        onClick={isCodeExercise && codeTestsPassed ? onContinue : onSubmit}
        disabled={exercisePhase === 'checking'}>
        {exercisePhase === 'checking' ? 'Saving…' : continueLabel}
      </button>
    )
  }

  const renderMcq = () => (
    <div className="exercise-options-grid">
      {(opts.length > 0 ? opts : exType === 'true_false' ? ['True', 'False'] : []).map((opt: string) => (
        <button key={opt}
          className={`exercise-option-btn ${exState.answer === opt ? 'selected' : ''}`}
          disabled={disabled}
          onClick={() => setState({ answer: opt })}
        >{opt}</button>
      ))}
    </div>
  )

  const renderFillBlank = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {((exercise.blanks && exercise.blanks.length > 0) ? exercise.blanks : ['_']).map((_: any, idx: number) => (
        <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <label style={{ fontWeight: 700, fontSize: '14px' }}>Blank {idx + 1}:</label>
          <input type="text" value={exState.answers?.[idx] || exState.answer || ''}
            placeholder="Type answer here..." disabled={disabled}
            onChange={(e) => {
              const val = e.target.value
              onInputChange((prev: any) => {
                const curAns = [...(prev[exercise.id]?.answers || [])]
                curAns[idx] = val
                return { ...prev, [exercise.id]: { ...prev[exercise.id], answers: curAns, answer: curAns[0] } }
              })
            }}
            style={{ padding: '8px 12px', borderRadius: '8px', border: '2px solid var(--line)', fontWeight: 700, fontSize: '14px', background: 'var(--input-bg)', color: 'var(--ink)' }}
          />
        </div>
      ))}
    </div>
  )

  const renderSelectMultiple = () => (
    <div className="exercise-options-grid">
      {opts.map((opt: string) => {
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

  const renderCode = () => {
    const starter = exercise.starter_code || exercise.code || ''
    const value = exState.code ?? starter
    return (
      <div className="exercise-code-block">
        <label className="exercise-code-label" htmlFor={`code-input-${exercise.id}`}>
          Your code:
        </label>
        <textarea
          id={`code-input-${exercise.id}`}
          className="exercise-code-textarea"
          value={value}
          disabled={disabled}
          spellCheck={false}
          rows={Math.min(10, Math.max(3, (value || starter).split("\n").length + 2))}
          aria-label="Your code answer"
          placeholder="Write your code here…"
          onChange={(e) => setState({ code: e.target.value })}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.shiftKey) && e.key === 'Enter') {
              e.preventDefault()
              if (props.onRunCode && !disabled && !props.isRunningCode) {
                props.onRunCode()
              }
              return
            }
            if (e.key === 'Tab') {
              e.preventDefault()
              const target = e.target as HTMLTextAreaElement
              const start = target.selectionStart
              const end = target.selectionEnd
              const next = value.substring(0, start) + '    ' + value.substring(end)
              setState({ code: next })
              requestAnimationFrame(() => {
                target.selectionStart = target.selectionEnd = start + 4
              })
            }
          }}
        />
        <div className="exercise-code-actions">
          {props.onRunCode && (
            <button
              type="button"
              className="duo-button duo-button-primary"
              disabled={disabled || props.isRunningCode}
              onClick={props.onRunCode}
            >
              {props.isRunningCode ? 'Running…' : 'Run code'}
            </button>
          )}
          <button
            type="button"
            className="duo-button duo-button-secondary exercise-code-reset"
            disabled={disabled || !starter}
            onClick={() => setState({ code: starter })}
          >
            Reset to starter
          </button>
        </div>
      </div>
    )
  }

  const renderOrdering = () => {
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

  const renderMatching = () => {
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

  const renderGeneric = () => (
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

  const renderAnswerInput = () => {
    if (MCQ_TYPES.includes(exType)) return renderMcq()
    if (FILL_TYPES.includes(exType) && usesInlineCodeEditor(exercise)) return renderCode()
    if (FILL_TYPES.includes(exType)) return renderFillBlank()
    if (exType === 'select_multiple') return renderSelectMultiple()
    if (exType === 'ordering') return renderOrdering()
    if (exType === 'matching') return renderMatching()
    if (CODE_TYPES.includes(exType)) return renderCode()
    return renderGeneric()
  }

  const showStarterBlock =
    (exercise.starter_code || exercise.code) &&
    !CODE_TYPES.includes(exType) &&
    !usesInlineCodeEditor(exercise)

  return (
    <div className="exercise-interactive-box">
      {renderInfo()}
      {renderMicroInstruction()}
      <h3 style={{ fontSize: '18px', fontWeight: 800, marginBottom: '12px', color: 'var(--ink)' }}>
        {exercise.question || exercise.title || 'Complete the exercise:'}
      </h3>
      {showStarterBlock && (
        <pre style={{
          background: 'var(--bg-code, #1e293b)',
          color: '#f8fafc',
          padding: '12px 16px',
          borderRadius: '8px',
          fontFamily: 'var(--font-mono, monospace)',
          fontSize: '14px',
          marginBottom: '16px',
          overflowX: 'auto',
          whiteSpace: 'pre-wrap'
        }}>
          <code>{exercise.starter_code || exercise.code}</code>
        </pre>
      )}
      {renderAnswerInput()}
      {renderOptionalDeepDive()}
      {renderCta()}
    </div>
  )
}

export default ExercisePanel
