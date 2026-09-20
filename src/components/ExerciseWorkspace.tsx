import React, { useMemo, useState } from 'react'
import { CodeEditor } from './CodeEditor'
import { type TerminalRunOutput } from './ExerciseCodeTerminal'
import { ExerciseFeedback } from './ExerciseFeedback'
import {
  assembleFillBlankCode,
  blankCount,
  buildFillBlankTemplate,
  extractAnswersFromEdited,
} from '../utils/assembleFillBlankCode'

const CODE_TYPES = ['code', 'tiny_coding', 'identify_mistake']
const FILL_TYPES = ['fill_blank', 'code_completion']

type TestResult = {
  name: string
  passed: boolean
  required: boolean
  description?: string
  error?: string | null
}

export interface ExerciseWorkspaceProps {
  exercise: any
  exType: string
  exerciseInput: Record<string, any>
  exercisePhase: string
  exerciseFeedback: any
  exercisePosition: number
  exerciseTotal: number
  completedExerciseCount: number
  onInputChange: (updater: any) => void
  onSubmit: () => void
  onContinue: () => void
  onRetry: () => void
  onRun?: () => void
  isRunning?: boolean
  onBack: () => void
  soundEnabled: boolean
  onToggleSound: () => void
  lessonId?: string | null
  runResults?: TestResult[] | null
  language?: string
}

function renderInlineCode(text: string): React.ReactNode[] {
  const parts = text.split(/(`[^`]+`)/g)
  return parts.map((part, i) =>
    part.startsWith('`') && part.endsWith('`')
      ? <code key={i} className="ew-task-code">{part.slice(1, -1)}</code>
      : part
  )
}

function pushUnique(steps: string[], value?: string | null) {
  const text = (value || '').trim()
  if (!text) return
  if (steps.some((step) => step.toLowerCase() === text.toLowerCase())) return
  steps.push(text)
}

export function getTaskSteps(exercise: any): string[] {
  if (Array.isArray(exercise.instructions) && exercise.instructions.length > 0) {
    return exercise.instructions.map(String).filter((s) => s.trim())
  }
  if (typeof exercise.instructions === 'string' && exercise.instructions.trim()) {
    return [exercise.instructions.trim()]
  }

  const steps: string[] = []
  pushUnique(steps, exercise.micro_explanation)

  const blanks = Array.isArray(exercise.blanks) ? exercise.blanks.filter(Boolean) : []
  blanks.forEach((blank: string) => {
    pushUnique(steps, `Fill in the blank with \`${blank}\`.`)
  })

  pushUnique(steps, exercise.worked_example_takeaway)

  if (Array.isArray(exercise.hints)) {
    exercise.hints.slice(0, 3 - steps.length).forEach((hint: string) => pushUnique(steps, hint))
  }

  return steps
}

export function formatTaskTitle(exercise: any, position: number): string {
  const raw = String(exercise.sublessonTitle || exercise.title || '').trim()
  const cleaned = raw.replace(/^step\s*[a-z0-9]+:\s*/i, '').trim()
  if (cleaned) return `Step ${position}: ${cleaned}`

  const question = String(exercise.question || '').replace(/:$/, '').trim()
  const calc = question.match(/calculate\s+[`']?([a-z_][a-z0-9_]*)/i)
  if (calc) return `Step ${position}: Calculate ${calc[1]}`
  if (question && question.length <= 42) return `Step ${position}: ${question}`
  return `Step ${position}: Complete the exercise`
}

export function exerciseFilename(exercise: any, language = 'python'): string {
  const extMap: Record<string, string> = {
    python: 'py',
    javascript: 'js',
    typescript: 'ts',
    java: 'java',
    cpp: 'cpp',
    sql: 'sql',
  }
  const ext = extMap[language] || 'py'
  const source = formatTaskTitle(exercise, 1)
    .replace(/^step\s*\d+:\s*/i, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '')
    .slice(0, 28)
  if (source && source !== 'complete_the_exercise') return `${source}.${ext}`
  return `exercise.${ext}`
}

function emptyFillCode(fillTemplate: string): string {
  const needed = blankCount(fillTemplate)
  const empty = Array.from({ length: needed }, () => '')
  return assembleFillBlankCode(fillTemplate, empty)
}

function codeStarter(exercise: any, isFill: boolean, fillTemplate: string): string {
  if (isFill) return emptyFillCode(fillTemplate)
  const raw = (exercise.starter_code || exercise.code || '').trim()
  if (!raw || raw === 'None') return '# Build your solution here\n'
  return exercise.starter_code || exercise.code || ''
}

export const ExerciseWorkspace: React.FC<ExerciseWorkspaceProps> = ({
  exercise,
  exType,
  exerciseInput,
  exercisePhase,
  exerciseFeedback,
  exercisePosition,
  exerciseTotal,
  completedExerciseCount,
  onInputChange,
  onSubmit,
  onContinue,
  onRetry,
  onRun,
  isRunning = false,
  onBack,
  soundEnabled,
  onToggleSound,
  lessonId,
  runResults,
  language = 'python',
}) => {
  const [showFeedbackPanel, setShowFeedbackPanel] = useState(false)
  const [outputCleared, setOutputCleared] = useState(false)

  const exState = exerciseInput[exercise.id] || {}
  const disabled = exercisePhase === 'checking' || exercisePhase === 'correct'
  const isFill = FILL_TYPES.includes(exType)

  const pct = exerciseTotal > 0 ? (completedExerciseCount / exerciseTotal) * 100 : 0
  const taskSteps = useMemo(() => getTaskSteps(exercise), [exercise])
  const filename = exerciseFilename(exercise, language)

  const fillTemplate = useMemo(
    () =>
      buildFillBlankTemplate(
        exercise.starter_code || exercise.code || '',
        exercise.blanks,
        exercise.question
      ),
    [exercise]
  )

  const initialCode = useMemo(
    () => codeStarter(exercise, isFill, fillTemplate),
    [exercise, isFill, fillTemplate]
  )

  const editorValue = (() => {
    const raw = exState.code ?? initialCode
    if (isFill && String(raw).includes('___')) {
      if (Array.isArray(exState.answers) && exState.answers.some(Boolean)) {
        return assembleFillBlankCode(fillTemplate, exState.answers)
      }
      return initialCode
    }
    return raw
  })()

  const runOutput: TerminalRunOutput | null = exState.runOutput ?? null

  const setState = (patch: Record<string, any>) => {
    onInputChange((prev: any) => ({ ...prev, [exercise.id]: { ...prev[exercise.id], ...patch } }))
  }

  const handleEditorChange = (value: string) => {
    if (isFill) {
      const answers = extractAnswersFromEdited(fillTemplate, value)
      setState({ code: value, answers, answer: answers[0] ?? '' })
      return
    }
    setState({ code: value })
  }

  const handleReset = () => {
    if (isFill) {
      const empty = Array.from({ length: blankCount(fillTemplate) }, () => '')
      setState({
        code: emptyFillCode(fillTemplate),
        answers: empty,
        answer: '',
        runOutput: null,
      })
    } else {
      setState({ code: initialCode, runOutput: null })
    }
    setOutputCleared(false)
  }

  const handleRun = () => {
    setOutputCleared(false)
    onRun?.()
  }

  const taskTitle = formatTaskTitle(exercise, exercisePosition)

  const rawQuestion = String(exercise.question || exercise.description || '').trim()
  const titleBody = taskTitle.replace(/^step\s*\d+:\s*/i, '').trim().toLowerCase()
  const taskDescription =
    rawQuestion && rawQuestion.replace(/:$/, '').trim().toLowerCase() !== titleBody
      ? rawQuestion
      : ''

  const renderOutput = () => {
    if (outputCleared) {
      return null
    }

    if (isRunning) {
      return <p className="ew-output-running">Running…</p>
    }

    if (runResults && runResults.length > 0) {
      return (
        <div className="ew-output-tests">
          {runResults.map((r) => (
            <div key={r.name} className={`ew-output-test ${r.passed ? 'pass' : 'fail'}`}>
              <span className="ew-output-test-icon" aria-hidden="true">{r.passed ? '✓' : '×'}</span>
              <span className="ew-output-test-name">{r.description || r.name}</span>
              {!r.passed && r.error && <span className="ew-output-test-error">{r.error}</span>}
            </div>
          ))}
        </div>
      )
    }

    if (runOutput?.stdout?.trim()) {
      return <pre className="ew-output-line">{runOutput.stdout.trim()}</pre>
    }
    if (runOutput?.stderr?.trim()) {
      return <pre className="ew-output-line ew-output-stderr">{runOutput.stderr.trim()}</pre>
    }
    if (runOutput?.error) {
      return <pre className="ew-output-line ew-output-error">{runOutput.error}</pre>
    }

    return null
  }

  const renderPrimaryAction = () => {
    if (exercisePhase === 'correct' && exerciseFeedback) {
      return (
        <button type="button" className="ew-btn ew-btn-submit" onClick={onContinue}>
          CONTINUE
        </button>
      )
    }
    if (exercisePhase === 'incorrect' && exerciseFeedback) {
      return (
        <button type="button" className="ew-btn ew-btn-submit" onClick={onRetry}>
          TRY AGAIN
        </button>
      )
    }
    return (
      <button
        type="button"
        className="ew-btn ew-btn-submit"
        onClick={onSubmit}
        disabled={exercisePhase === 'checking'}
      >
        {exercisePhase === 'checking' ? 'CHECKING…' : 'SUBMIT'}
      </button>
    )
  }

  return (
    <div className="ew-root" aria-label="Coding exercise workspace">
      <header className="ew-topbar">
        <button type="button" className="ew-close" onClick={onBack} aria-label="Exit exercise">
          ✕
        </button>
        <div
          className="ew-progress"
          role="progressbar"
          aria-label="Lesson progress"
          aria-valuenow={completedExerciseCount}
          aria-valuemin={0}
          aria-valuemax={exerciseTotal}
        >
          <div className="ew-progress-fill" style={{ width: `${pct}%` }} />
        </div>
        <div className="ew-topbar-actions">
          <button
            type="button"
            className="ew-topbar-link"
            onClick={() => setShowFeedbackPanel((v) => !v)}
            aria-expanded={showFeedbackPanel}
          >
            <span className="ew-topbar-icon" aria-hidden="true">💬</span> Feedback
          </button>
          <button
            type="button"
            className="ew-topbar-link"
            onClick={onToggleSound}
            aria-label={soundEnabled ? 'Mute audio' : 'Unmute audio'}
          >
            <span className="ew-topbar-icon" aria-hidden="true">{soundEnabled ? '🔊' : '🔇'}</span> Audio
          </button>
        </div>
      </header>

      {showFeedbackPanel && (
        <div className="ew-feedback-dropdown">
          <ExerciseFeedback
            exerciseId={exercise.id}
            lessonId={lessonId ?? null}
            reportOnly={exercisePhase === 'incorrect'}
          />
        </div>
      )}

      <div className="ew-body">
        <aside className="ew-task-col" aria-label="Task instructions">
          <span className="ew-section-label">Learn</span>
          <div className="ew-task-card">
            <div className="ew-task-badge">
              <span className="ew-task-badge-icon" aria-hidden="true">📋</span> YOUR TASK
            </div>
            <h2 className="ew-task-title">{taskTitle}</h2>
            {taskDescription && <p className="ew-task-desc">{taskDescription}</p>}
            {taskSteps.length > 0 && (
              <ol className="ew-task-steps">
                {taskSteps.map((step, idx) => (
                  <li key={idx}>
                    <span className="ew-step-num">{idx + 1}</span>
                    <span className="ew-step-text">{renderInlineCode(step)}</span>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </aside>

        <div className="ew-workspace-pane">
          <div className="ew-workspace-columns">
            <main className="ew-editor-col" aria-label="Code editor">
              <div className="ew-editor-shell">
                <CodeEditor
                  value={editorValue}
                  onChange={handleEditorChange}
                  disabled={disabled}
                  filename={filename}
                  variant="workspace"
                  onKeyDown={(e) => {
                    if ((e.ctrlKey || e.shiftKey) && e.key === 'Enter') {
                      e.preventDefault()
                      handleRun()
                    }
                  }}
                />
                <button
                  type="button"
                  className="ew-editor-reset"
                  onClick={handleReset}
                  disabled={disabled}
                  aria-label="Reset code"
                  title="Reset code"
                >
                  ↺
                </button>
              </div>
            </main>

            <aside className="ew-output-col" aria-label="Output">
              <div className="ew-output-header">
                <span className="ew-output-label">Output</span>
                <button
                  type="button"
                  className="ew-output-clear"
                  onClick={() => setOutputCleared(true)}
                  aria-label="Clear output"
                  title="Clear output"
                >
                  🗑
                </button>
              </div>
              <div className="ew-output-body" aria-live="polite">
                {renderOutput()}
              </div>
            </aside>
          </div>

          {(exercisePhase === 'correct' || exercisePhase === 'incorrect') && exerciseFeedback && (
            <div className={`ew-grade-banner ${exercisePhase}`} role="status">
              <span className="ew-grade-title">
                {exercisePhase === 'correct' ? 'Correct!' : 'Not quite'}
              </span>
              <span className="ew-grade-text">{exerciseFeedback.feedback}</span>
              {exercisePhase === 'correct' && exerciseFeedback.xpAwarded > 0 && (
                <span className="ew-grade-xp">+{exerciseFeedback.xpAwarded} XP</span>
              )}
            </div>
          )}

          <footer className="ew-footer">
            <div className="ew-footer-left">
              <button type="button" className="ew-btn ew-btn-back" onClick={onBack}>
                <span aria-hidden="true">←</span> BACK
              </button>
            </div>
            <div className="ew-footer-right">
              {onRun && (
                <button
                  type="button"
                  className="ew-btn ew-btn-run"
                  onClick={handleRun}
                  disabled={disabled || isRunning}
                >
                  <span aria-hidden="true">▷</span> {isRunning ? 'RUNNING…' : 'RUN'}
                </button>
              )}
              {renderPrimaryAction()}
            </div>
          </footer>
        </div>
      </div>
    </div>
  )
}

export default ExerciseWorkspace
