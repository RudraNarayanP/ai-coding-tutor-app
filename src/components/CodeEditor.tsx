import React, { useEffect, useRef, useState } from 'react'

export type TerminalRunOutput = {
  stdout?: string
  stderr?: string
  error?: string | null
}

interface CodeEditorProps {
  value: string
  onChange: (value: string) => void
  onKeyDown?: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void
  disabled?: boolean
  filename?: string
  variant?: 'default' | 'workspace'
  ariaLabel?: string
  showHeader?: boolean
}

// Shared full-pane editor used by Learn, Practice, Create, and lesson workspaces.
export const CodeEditor: React.FC<CodeEditorProps> = ({
  value,
  onChange,
  onKeyDown,
  disabled = false,
  filename = 'exercise.py',
  variant = 'default',
  ariaLabel = 'Code editor',
  showHeader = true,
}) => {
  const bodyRef = useRef<HTMLDivElement>(null)
  const [fittedLines, setFittedLines] = useState(24)
  const contentLines = Math.max(1, value.split('\n').length)
  const lineCount = Math.max(contentLines, fittedLines)

  useEffect(() => {
    const el = bodyRef.current
    if (!el) return

    const update = () => {
      const lineHeight = 24
      const padding = 32
      const next = Math.floor((el.clientHeight - padding) / lineHeight)
      if (next > 0) setFittedLines(next)
    }

    update()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(update)
    observer.observe(el)
    return () => observer.disconnect()
  }, [variant])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (onKeyDown) {
      onKeyDown(e)
    }
    if ((e.ctrlKey && e.key === 'Enter') || (e.shiftKey && e.key === 'Enter')) {
      e.preventDefault()
      window.dispatchEvent(new CustomEvent('patchwork:run'))
      return
    }
    if (e.key === 'Tab') {
      e.preventDefault()
      const target = e.target as HTMLTextAreaElement
      const start = target.selectionStart
      const end = target.selectionEnd
      const newValue = value.substring(0, start) + '    ' + value.substring(end)
      onChange(newValue)
      requestAnimationFrame(() => {
        target.selectionStart = target.selectionEnd = start + 4
      })
    }
  }

  return (
    <div className={`code-editor${variant === 'workspace' ? ' code-editor--workspace' : ''}`}>
      {showHeader && (
        <div className="code-editor-header">
          <span className="code-editor-filename">
            {filename}
          </span>
        </div>
      )}
      <div ref={bodyRef} className="code-editor-body">
        <div className="line-numbers" aria-hidden="true">
          {Array.from({ length: lineCount }, (_, i) => (
            <div key={i} className="line-number">
              {i + 1}
            </div>
          ))}
        </div>
        <div className="code-editor-input">
          <textarea
            className="code-editor-textarea"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            readOnly={disabled}
            spellCheck={false}
            aria-label={ariaLabel}
            role="textbox"
          />
        </div>
      </div>
    </div>
  )
}
