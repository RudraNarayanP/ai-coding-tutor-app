import React, { useEffect, useRef } from 'react'

export type TerminalLineKind = 'command' | 'stdout' | 'stderr' | 'info' | 'error'

export type TerminalLine = {
  id: string
  kind: TerminalLineKind
  text: string
}

export interface ProjectTerminalProps {
  cwd: string
  lines: TerminalLine[]
  command: string
  running: boolean
  height: number
  onCommandChange: (value: string) => void
  onSubmit: () => void
  onRunProject: () => void
  onClear: () => void
  onHistory: (direction: -1 | 1) => void
  onResizeStart: (event: React.MouseEvent) => void
}

let lineCounter = 0

export function makeTerminalLine(kind: TerminalLineKind, text: string): TerminalLine {
  lineCounter += 1
  return { id: `t-${lineCounter}`, kind, text }
}

export function shellPrompt(cwd: string): string {
  const path = cwd === '/workspace' ? '~' : cwd.replace(/^\/workspace/, '~')
  return `student@patchwork:${path}$`
}

export const ProjectTerminal: React.FC<ProjectTerminalProps> = ({
  cwd,
  lines,
  command,
  running,
  height,
  onCommandChange,
  onSubmit,
  onRunProject,
  onClear,
  onHistory,
  onResizeStart,
}) => {
  const bodyRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  useEffect(() => {
    const body = bodyRef.current
    if (!body) return
    body.scrollTop = body.scrollHeight
  }, [lines, running, command])

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'l' && event.ctrlKey) {
      event.preventDefault()
      onClear()
      return
    }
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      onSubmit()
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      onHistory(-1)
      return
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      onHistory(1)
    }
  }

  const pathLabel = cwd === '/workspace' ? '~' : cwd.replace(/^\/workspace/, '~')

  return (
    <section className="pw-terminal" aria-label="Terminal" style={{ height }}>
      <button
        type="button"
        className="pw-terminal-resize"
        aria-label="Resize terminal"
        onMouseDown={onResizeStart}
      />
      <div className="pw-terminal-header">
        <div className="pw-terminal-tabs" role="tablist" aria-label="Panel">
          <button type="button" className="pw-terminal-tab" disabled>
            Problems
          </button>
          <button type="button" className="pw-terminal-tab" disabled>
            Output
          </button>
          <button type="button" className="pw-terminal-tab" disabled>
            Debug Console
          </button>
          <button type="button" className="pw-terminal-tab active" role="tab" aria-selected="true">
            Terminal
          </button>
        </div>
        <div className="pw-terminal-actions">
          <span className="pw-terminal-shell" title="Shell">
            1: bash
          </span>
          <button
            type="button"
            className="pw-terminal-icon"
            onClick={onRunProject}
            disabled={running}
            title="Run Active File"
            aria-label="Run project"
          >
            ▷
          </button>
          <button
            type="button"
            className="pw-terminal-icon"
            onClick={onClear}
            title="Clear Terminal"
            aria-label="Clear terminal"
          >
            ⌧
          </button>
        </div>
      </div>

      <div
        ref={bodyRef}
        className="pw-terminal-body"
        onClick={() => inputRef.current?.focus()}
      >
        {lines.map((line) => (
          <div key={line.id} className={`pw-terminal-line pw-terminal-${line.kind}`}>
            {line.text}
          </div>
        ))}
        <div className={`pw-terminal-active${running ? ' is-running' : ''}`}>
          <span className="pw-terminal-prompt">
            <span className="pw-terminal-user">student@patchwork</span>
            <span className="pw-terminal-colon">:</span>
            <span className="pw-terminal-path">{pathLabel}</span>
            <span className="pw-terminal-hash">$ </span>
          </span>
          <input
            ref={inputRef}
            className="pw-terminal-input"
            value={command}
            onChange={(e) => onCommandChange(e.target.value)}
            onKeyDown={handleKeyDown}
            aria-label="Terminal command"
            disabled={running}
            autoComplete="off"
            spellCheck={false}
            autoCapitalize="off"
            autoCorrect="off"
          />
        </div>
      </div>
    </section>
  )
}
