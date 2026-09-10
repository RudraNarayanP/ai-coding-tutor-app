import React from 'react'

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
}

const ExercisePanel: React.FC<Props> = (props) => {
  const {exercise, exerciseInput, exercisePhase, exerciseFeedback, exercisePosition, exerciseTotal, completedExerciseCount, onInputChange, onSubmit, onContinue, onRetry, onRunCode, isRunningCode} = props
  const exType = (exercise.type || 'code').toLowerCase().trim()
  const opts = exercise.options || []
  const exState = exerciseInput[exercise.id] || {}
  const disabled = exercisePhase === 'checking' || exercisePhase === 'correct'

  const pct = exerciseTotal > 0 ? (completedExerciseCount / exerciseTotal) * 100 : 0

  const renderInfo = () => (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
        <span style={{ fontWeight: 800, fontSize: '14px', color: 'var(--ink-soft)' }}>
          Exercise {exercisePosition} of {exerciseTotal}
        </span>
        <span style={{ fontWeight: 700, fontSize: '13px', color: '#64748b' }}>
          {completedExerciseCount} / {exerciseTotal} complete
        </span>
      </div>
      <div style={{ height: '8px', borderRadius: '4px', background: '#e2e8f0', overflow: 'hidden', marginBottom: '16px' }}
        role="progressbar" aria-label="Lesson progress"
        aria-valuenow={completedExerciseCount} aria-valuemin={0} aria-valuemax={exerciseTotal}>
        <div style={{ height: '100%', width: `${pct}%`, background: '#16a34a', transition: 'width 0.3s' }} />
      </div>
    </div>
  )

  const renderCta = () => {
    if (exercisePhase === 'correct' && exerciseFeedback) {
      return (
        <div className="duo-feedback-panel success" style={{ marginTop: '16px' }}>
          <div className="duo-feedback-title"><span>&check; Correct!</span></div>
          <p style={{ fontWeight: 700 }}>{exerciseFeedback.feedback}</p>
          <button className="duo-button duo-button-primary" style={{ marginTop: '12px', padding: '12px 24px' }} onClick={onContinue}>Continue &rarr;</button>
        </div>
      )
    }
    if (exercisePhase === 'incorrect' && exerciseFeedback) {
      return (
        <div className="duo-feedback-panel error" style={{ marginTop: '16px' }}>
          <div className="duo-feedback-title"><span>&#10007; Not quite</span></div>
          <p style={{ fontWeight: 700 }}>{exerciseFeedback.feedback}</p>
          <button className="duo-button duo-button-primary" style={{ marginTop: '12px', padding: '12px 24px' }} onClick={onRetry}>Try Again</button>
        </div>
      )
    }
    return (
      <button className="duo-button duo-button-primary" style={{ marginTop: '16px', padding: '12px 24px' }}
        onClick={onSubmit} disabled={exercisePhase === 'checking'}>
        {exercisePhase === 'checking' ? 'Checking...' : 'Check Answer'}
      </button>
    )
  }

  const renderMcq = () => (
    <div className="exercise-options-grid">
      {(opts.length > 0 ? opts : exType === 'true_false' ? ['True', 'False'] : []).map((opt: string) => (
        <button key={opt}
          className={`exercise-option-btn ${exState.answer === opt ? 'selected' : ''}`}
          disabled={disabled}
          onClick={() => onInputChange((prev: any) => ({ ...prev, [exercise.id]: { ...prev[exercise.id], answer: opt } }))}
        >{opt}</button>
      ))}
    </div>
  )

  const renderFillBlank = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {((exercise.blanks && exercise.blanks.length > 0) ? exercise.blanks : ['_']).map((_: string, idx: number) => (
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
            style={{ padding: '8px 12px', borderRadius: '8px', border: '2px solid var(--line)', fontWeight: 700, fontSize: '14px' }}
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
              onInputChange((prev: any) => ({ ...prev, [exercise.id]: { ...prev[exercise.id], answers: Array.from(n) } }))
            }}
            disabled={disabled}
          >{sel ? '☑ ' : '☐ '}{opt}</button>
        )
      })}
    </div>
  )

  return (
    <div className="exercise-interactive-box">
      {renderInfo()}
      <h3 style={{ fontSize: '18px', fontWeight: 800, marginBottom: '12px' }}>
        {exercise.question || exercise.title || 'Complete the exercise:'}
      </h3>
      {['mcq', 'true_false', 'output_prediction', 'debugging', 'identify_error'].includes(exType) && renderMcq()}
      {['fill_blank', 'code_completion'].includes(exType) && renderFillBlank()}
      {exType === 'select_multiple' && renderSelectMultiple()}
      {renderCta()}
    </div>
  )
}

export default ExercisePanel
