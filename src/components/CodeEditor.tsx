import React from 'react'

interface CodeEditorProps {
  value: string
  onChange: (value: string) => void
  onKeyDown?: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void
  disabled?: boolean
  filename?: string
}

// ─── CodeEditor ──────────────────────────────────────────────────────────────
// Textarea-based editor with a synchronized line-number gutter. Preserves the
// keyboard contract the tests rely on:
//   - Tab inserts indentation
//   - Ctrl+Enter / Shift+Enter triggers onRun

export const CodeEditor: React.FC<CodeEditorProps> = ({
  value,
  onChange,
  onKeyDown,
  disabled = false,
  filename = 'exercise.py',
}) => {
  const lineCount = value.split('\n').length

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (onKeyDown) {
      onKeyDown(e)
    }
    // Expose a run callback via a custom event so App stays in control.
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
    <div className="code-editor">
      <div className="code-editor-header">
        <span className="code-editor-filename">{filename}</span>
      </div>
      <div className="code-editor-body">
        <div className="line-numbers" aria-hidden="true">
          {Array.from({ length: lineCount }, (_, i) => (
            <div key={i} className="line-number">
              {i + 1}
            </div>
          ))}
        </div>
        <textarea
          className="code-editor-textarea"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          spellCheck={false}
          aria-label="Code editor"
          role="textbox"
        />
      </div>
    </div>
  )
}