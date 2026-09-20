import React, { useEffect, useRef } from 'react'

const BLANK_TOKEN = '___'

export type TerminalRunOutput = {
  stdout?: string
  stderr?: string
  error?: string | null
}

export interface ExerciseCodeTerminalProps {
  code: string
  answers: string[]
  disabled?: boolean
  isRunning?: boolean
  runOutput?: TerminalRunOutput | null
  onAnswerChange: (index: number, value: string) => void
  onRun?: () => void
  /** When true, output is rendered externally (e.g. in ExerciseWorkspace output panel). */
  hideOutput?: boolean
  filename?: string
  variant?: 'default' | 'workspace'
}

function blankCount(code: string): number {
  if (!code.includes(BLANK_TOKEN)) return 0
  return code.split(BLANK_TOKEN).length - 1
}

export const ExerciseCodeTerminal: React.FC<ExerciseCodeTerminalProps> = ({
  code,
  answers,
  disabled = false,
  isRunning = false,
  runOutput = null,
  onAnswerChange,
  onRun,
  hideOutput = false,
  filename = 'exercise.py',
  variant = 'default',
}) => {
  const bodyRef = useRef<HTMLDivElement>(null)
  const inputRefs = useRef<Array<HTMLInputElement | null>>([])
  const parts = code.split(BLANK_TOKEN)
  const totalBlanks = blankCount(code)

  useEffect(() => {
    const body = bodyRef.current
    if (!body) return
    body.scrollTop = body.scrollHeight
  }, [runOutput, isRunning])

  const focusBlank = (index: number) => {
    inputRefs.current[index]?.focus()
  }

  const handleKeyDown = (index: number, event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' && event.shiftKey) {
      event.preventDefault()
      onRun?.()
      return
    }
    if (event.key === 'Tab' && !event.shiftKey && index < totalBlanks - 1) {
      event.preventDefault()
      focusBlank(index + 1)
    }
    if (event.key === 'Tab' && event.shiftKey && index > 0) {
      event.preventDefault()
      focusBlank(index - 1)
    }
  }

  const hasOutput = !hideOutput && Boolean(
    runOutput?.stdout?.trim() ||
    runOutput?.stderr?.trim() ||
    runOutput?.error
  )

  return (
    <section
      className={`pw-terminal exercise-code-terminal${variant === 'workspace' ? ' exercise-code-terminal--workspace' : ''}`}
      aria-label="Code terminal"
    >
      <div className="pw-terminal-header ew-editor-tab-bar">
        <div className="pw-terminal-tabs" role="tablist" aria-label="Panel">
          <button type="button" className="pw-terminal-tab active ew-file-tab" role="tab" aria-selected="true">
            {filename}
          </button>
        </div>
        {!hideOutput && (
          <div className="pw-terminal-actions">
            <span className="pw-terminal-shell" title="Shell">python</span>
            {onRun && (
              <button
                type="button"
                className="pw-terminal-icon"
                onClick={onRun}
                disabled={disabled || isRunning}
                title="Run code (Shift+Enter)"
                aria-label="Run code"
              >
                ▷
              </button>
            )}
          </div>
        )}
      </div>

      <div ref={bodyRef} className="pw-terminal-body exercise-code-terminal-body">
        <pre className="exercise-code-terminal-pre">
          <code>
            {parts.map((part, idx) => (
              <React.Fragment key={idx}>
                {part}
                {idx < parts.length - 1 && (
                  <input
                    ref={(el) => { inputRefs.current[idx] = el }}
                    type="text"
                    className="exercise-terminal-blank"
                    value={answers[idx] || ''}
                    disabled={disabled || isRunning}
                    spellCheck={false}
                    autoComplete="off"
                    autoCapitalize="off"
                    autoCorrect="off"
                    aria-label={`Blank ${idx + 1}`}
                    size={Math.max(6, (answers[idx] || '').length + 2)}
                    onChange={(e) => onAnswerChange(idx, e.target.value)}
                    onKeyDown={(e) => handleKeyDown(idx, e)}
                  />
                )}
              </React.Fragment>
            ))}
          </code>
        </pre>

        {isRunning && <div className="pw-terminal-line pw-terminal-info">Running…</div>}

        {hasOutput && !isRunning && (
          <div className="exercise-code-terminal-output" aria-live="polite">
            {runOutput?.stdout?.trim() && (
              <div className="pw-terminal-line pw-terminal-stdout">{runOutput.stdout.trim()}</div>
            )}
            {runOutput?.stderr?.trim() && (
              <div className="pw-terminal-line pw-terminal-stderr">{runOutput.stderr.trim()}</div>
            )}
            {runOutput?.error && (
              <div className="pw-terminal-line pw-terminal-error">{runOutput.error}</div>
            )}
          </div>
        )}

        {!hideOutput && (
          <p className="exercise-code-terminal-hint">Shift+Enter to run · then Check Answer to continue</p>
        )}
      </div>
    </section>
  )
}

export default ExerciseCodeTerminal
