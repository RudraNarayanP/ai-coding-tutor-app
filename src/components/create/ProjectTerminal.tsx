import React, { useEffect, useRef, useState } from 'react'

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
  /** Workspace paths offered on Tab. */
  completions: string[]
  onCommandChange: (value: string) => void
  onSubmit: () => void
  onInterrupt: () => void
  onRunProject: () => void
  onClear: () => void
  onHistory: (direction: -1 | 1) => void
  onResizeStart: (event: React.MouseEvent) => void
  onCandidates: (matches: string[]) => void
}

// Escape sequences never render usefully in a log view, and pip/progress output
// rewrites its line with \r the way a terminal would.
const ANSI = /\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\x1b[()][A-Z0-9]|\x1b[=>78Mc]/g

export function sanitizeTerminalText(text: string): string {
  return text
    .replace(ANSI, '')
    .replace(/\r\n/g, '\n')
    .split('\n')
    .map((line) => (line.includes('\r') ? line.slice(line.lastIndexOf('\r') + 1) : line))
    .join('\n')
    .replace(/\s+$/, '')
}

let lineCounter = 0

export function makeTerminalLine(kind: TerminalLineKind, text: string): TerminalLine {
  lineCounter += 1
  return { id: `t-${lineCounter}`, kind, text: sanitizeTerminalText(text) }
}

export function shellPrompt(cwd: string): string {
  const path = cwd === '/workspace' ? '~' : cwd.replace(/^\/workspace/, '~')
  return `student@patchwork:${path}$`
}

/** Complete the word under the caret against `candidates`, bash-style. */
export function completeWord(
  command: string,
  caret: number,
  candidates: string[]
): { command: string; caret: number; matches: string[] } {
  const start = command.lastIndexOf(' ', caret - 1) + 1
  const word = command.slice(start, caret)
  if (!word) return { command, caret, matches: [] }

  const matches = candidates.filter((c) => c.startsWith(word))
  if (matches.length === 0) return { command, caret, matches: [] }

  let common = matches[0]
  for (const candidate of matches.slice(1)) {
    let i = 0
    while (i < common.length && i < candidate.length && common[i] === candidate[i]) i += 1
    common = common.slice(0, i)
  }
  if (common.length <= word.length) return { command, caret, matches }

  return {
    command: command.slice(0, start) + common + command.slice(caret),
    caret: start + common.length,
    matches,
  }
}

export const ProjectTerminal: React.FC<ProjectTerminalProps> = ({
  cwd,
  lines,
  command,
  running,
  height,
  completions,
  onCommandChange,
  onSubmit,
  onInterrupt,
  onRunProject,
  onClear,
  onHistory,
  onResizeStart,
  onCandidates,
}) => {
  const bodyRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const lastTyped = useRef(command)
  const [caret, setCaret] = useState(command.length)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  // History recall and submit-clear change `command` from outside the input, so
  // the rendered block cursor has to follow to the end of the new line.
  useEffect(() => {
    if (lastTyped.current === command) return
    lastTyped.current = command
    const input = inputRef.current
    if (input) input.selectionStart = input.selectionEnd = command.length
    setCaret(command.length)
  }, [command])

  useEffect(() => {
    const body = bodyRef.current
    if (!body) return
    body.scrollTop = body.scrollHeight
  }, [lines, running, command])

  const syncCaret = () => {
    const input = inputRef.current
    if (input) setCaret(input.selectionStart ?? input.value.length)
  }

  const handleTab = (event: React.KeyboardEvent<HTMLInputElement>) => {
    event.preventDefault()
    const result = completeWord(command, caret, completions)
    if (result.matches.length === 0) return
    if (result.matches.length > 1) onCandidates(result.matches)
    if (result.command === command) return

    onCommandChange(result.command)
    lastTyped.current = result.command
    const input = inputRef.current
    if (input) {
      requestAnimationFrame(() => {
        input.selectionStart = input.selectionEnd = result.caret
        setCaret(result.caret)
      })
    }
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'l' && event.ctrlKey) {
      event.preventDefault()
      onClear()
      return
    }
    if (event.key === 'c' && event.ctrlKey) {
      event.preventDefault()
      onInterrupt()
      return
    }
    if (event.key === 'Tab') {
      handleTab(event)
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

  const prefix = command.slice(0, caret)
  const suffix = command.slice(caret)

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
            🗑
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
          <span className="pw-terminal-echo">
            <span className="pw-terminal-prompt">
              <span className="pw-terminal-user">student@patchwork</span>
              <span className="pw-terminal-colon">:</span>
              <span className="pw-terminal-path">{cwd === '/workspace' ? '~' : cwd.replace(/^\/workspace/, '~')}</span>
              <span className="pw-terminal-hash">$ </span>
            </span>
            <span className="pw-terminal-typed">
              {prefix}
              <span className="pw-terminal-cursor" aria-hidden="true">
                {suffix ? suffix[0] : '\u00a0'}
              </span>
              {suffix.slice(1)}
            </span>
          </span>
          <input
            ref={inputRef}
            className="pw-terminal-input"
            value={command}
            onChange={(e) => {
              lastTyped.current = e.target.value
              onCommandChange(e.target.value)
              setCaret(e.target.selectionStart ?? e.target.value.length)
            }}
            onKeyDown={handleKeyDown}
            onKeyUp={syncCaret}
            onClick={syncCaret}
            onSelect={syncCaret}
            aria-label="Terminal command"
            disabled={running}
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
            spellCheck={false}
          />
        </div>
      </div>
    </section>
  )
}
