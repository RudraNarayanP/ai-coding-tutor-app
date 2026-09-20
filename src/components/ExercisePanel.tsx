import React, { useState } from 'react'
import { ExerciseFeedback } from './ExerciseFeedback'
import { CodeEditor } from './CodeEditor'
import ExerciseWorkspace, { exerciseFilename } from './ExerciseWorkspace'
import LessonSourceNote, { type LessonSourceInfo } from './LessonSourceNote'
import {
  ExerciseAnswerInput,
  FILL_TYPES,
  CODE_TYPES,
} from './ExerciseAnswerInput'
import {
  assembleFillBlankCode,
  blankCount,
  buildFillBlankTemplate,
  extractAnswersFromEdited,
} from '../utils/assembleFillBlankCode'

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
  lessonId?: string | null
  onBack?: () => void
  soundEnabled?: boolean
  onToggleSound?: () => void
  runResults?: Array<{ name: string; passed: boolean; required: boolean; description?: string; error?: string | null }> | null
  language?: string
  /** Source attribution + objectives of the lesson this exercise belongs to. */
  lessonSource?: LessonSourceInfo | null
  lessonObjectives?: string[]
  combo?: number
  lessonType?: string
  /** Workspace slots so exercise steps get the same tutor chrome as lessons. */
  footerExtra?: React.ReactNode
  outputExtra?: React.ReactNode
  taskExtra?: React.ReactNode
  banner?: React.ReactNode
}

const ExercisePanel: React.FC<Props> = (props) => {
  const {exercise, exerciseInput, exercisePhase, exerciseFeedback, exercisePosition, exerciseTotal, completedExerciseCount, onInputChange, onSubmit, onContinue, onRetry, lessonId} = props
  const [showDeepDive, setShowDeepDive] = useState(false)
  const exType = (exercise.type || 'code').toLowerCase().trim()
  const exState = exerciseInput[exercise.id] || {}
  const disabled = exercisePhase === 'checking' || exercisePhase === 'correct'

  const pct = exerciseTotal > 0 ? (completedExerciseCount / exerciseTotal) * 100 : 0

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
          <button className="duo-button duo-button-primary" style={{ marginTop: '12px', padding: '12px 24px' }} onClick={onContinue}>Continue &rarr;</button>
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
    return (
      <button className="duo-button duo-button-primary" style={{ marginTop: '16px', padding: '12px 24px' }}
        onClick={onSubmit} disabled={exercisePhase === 'checking'}>
        {exercisePhase === 'checking' ? 'Checking...' : 'Check Answer'}
      </button>
    )
  }

  const renderFillBlank = () => {
    const template = buildFillBlankTemplate(
      exercise.starter_code || exercise.code || '',
      exercise.blanks,
      exercise.question
    )
    const empty = Array.from({ length: blankCount(template) }, () => '')
    const raw = exState.code
    const value = raw && !String(raw).includes('___')
      ? raw
      : assembleFillBlankCode(template, exState.answers?.length ? exState.answers : empty)

    return (
      <CodeEditor
        value={value}
        disabled={disabled}
        filename={exerciseFilename(exercise, props.language)}
        variant="workspace"
        onChange={(next) => {
          const answers = extractAnswersFromEdited(template, next)
          setState({ code: next, answers, answer: answers[0] ?? '' })
        }}
        onKeyDown={(e) => {
          if ((e.ctrlKey || e.shiftKey) && e.key === 'Enter') {
            e.preventDefault()
            props.onRunCode?.()
          }
        }}
      />
    )
  }

  const renderCode = () => {
    const rawStarter = exercise.starter_code || exercise.code || ''
    const starter = (rawStarter.includes("___") || rawStarter.includes("---")) ? '' : rawStarter
    const value = exState.code ?? starter
    return (
      <CodeEditor
        value={value}
        disabled={disabled}
        filename={exerciseFilename(exercise, props.language)}
        variant="workspace"
        ariaLabel="Your code answer"
        onChange={(next) => setState({ code: next })}
        onKeyDown={(e) => {
          if ((e.ctrlKey || e.shiftKey) && e.key === 'Enter') {
            e.preventDefault()
            props.onRunCode?.()
          }
        }}
      />
    )
  }

  const renderAnswerInput = () => {
    if (FILL_TYPES.includes(exType)) return renderFillBlank()
    if (CODE_TYPES.includes(exType)) return renderCode()
    return (
      <ExerciseAnswerInput
        exercise={exercise}
        exType={exType}
        exState={exState}
        disabled={disabled}
        setState={setState}
      />
    )
  }

  const showStarterBlock = (exercise.starter_code || exercise.code) && !CODE_TYPES.includes(exType) && !FILL_TYPES.includes(exType)

  if (props.onBack) {
    return (
      <ExerciseWorkspace
        exercise={exercise}
        exType={exType}
        exerciseInput={exerciseInput}
        exercisePhase={exercisePhase}
        exerciseFeedback={exerciseFeedback}
        exercisePosition={exercisePosition}
        exerciseTotal={exerciseTotal}
        completedExerciseCount={completedExerciseCount}
        onInputChange={onInputChange}
        onSubmit={onSubmit}
        onContinue={onContinue}
        onRetry={onRetry}
        onRun={props.onRunCode}
        isRunning={props.isRunningCode}
        onBack={props.onBack}
        soundEnabled={props.soundEnabled ?? true}
        onToggleSound={props.onToggleSound ?? (() => {})}
        lessonId={lessonId}
        runResults={props.runResults}
        language={props.language}
        lessonSource={props.lessonSource}
        lessonObjectives={props.lessonObjectives}
        combo={props.combo}
        lessonType={props.lessonType}
        footerExtra={props.footerExtra}
        outputExtra={props.outputExtra}
        taskExtra={props.taskExtra}
        banner={props.banner}
      />
    )
  }

  return (
    <div className="exercise-interactive-box">
      {renderInfo()}
      {renderMicroInstruction()}
      <LessonSourceNote source={props.lessonSource} objectives={props.lessonObjectives} />
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
