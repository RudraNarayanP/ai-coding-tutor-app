import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import type { ComponentProps } from 'react'
import {
  ProjectTerminal,
  completeWord,
  makeTerminalLine,
  sanitizeTerminalText,
} from './ProjectTerminal'

function setup(overrides: Partial<ComponentProps<typeof ProjectTerminal>> = {}) {
  const onSubmit = vi.fn()
  render(
    <ProjectTerminal
      cwd="/workspace"
      lines={[
        makeTerminalLine('command', 'student@patchwork:~$ ls'),
        makeTerminalLine('stdout', 'main.py'),
      ]}
      command="pip install requests"
      running={false}
      height={260}
      completions={['main.py', 'manifest.json']}
      onCommandChange={() => {}}
      onSubmit={onSubmit}
      onInterrupt={() => {}}
      onRunProject={() => {}}
      onClear={() => {}}
      onHistory={() => {}}
      onResizeStart={() => {}}
      onCandidates={() => {}}
      {...overrides}
    />
  )
  return { onSubmit }
}

describe('ProjectTerminal', () => {
  it('types on the live prompt line and submits with Enter', () => {
    const { onSubmit } = setup()

    expect(screen.getByText('Terminal')).toBeInTheDocument()
    expect(screen.getByText('1: bash')).toBeInTheDocument()
    expect(screen.getByText('student@patchwork')).toBeInTheDocument()
    const input = screen.getByLabelText('Terminal command') as HTMLInputElement
    expect(input.value).toBe('pip install requests')
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onSubmit).toHaveBeenCalled()
  })

  it('interrupts with Ctrl+C and clears with Ctrl+L', () => {
    const onInterrupt = vi.fn()
    const onClear = vi.fn()
    setup({ onInterrupt, onClear })
    const input = screen.getByLabelText('Terminal command')

    fireEvent.keyDown(input, { key: 'c', ctrlKey: true })
    expect(onInterrupt).toHaveBeenCalled()
    fireEvent.keyDown(input, { key: 'l', ctrlKey: true })
    expect(onClear).toHaveBeenCalled()
  })

  it('keeps arrow keys for command history instead of Tab handling', () => {
    const onHistory = vi.fn()
    setup({ onHistory })
    const input = screen.getByLabelText('Terminal command')

    fireEvent.keyDown(input, { key: 'ArrowUp' })
    expect(onHistory).toHaveBeenCalledWith(-1)
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    expect(onHistory).toHaveBeenCalledWith(1)
  })

  it('completes the word under the caret against workspace files', () => {
    const files = ['main.py', 'manifest.json']
    // Longest common prefix of both candidates: 'ma' -> 'm' grows to 'ma'.
    expect(completeWord('cat m', 5, files)).toEqual({
      command: 'cat ma',
      caret: 6,
      matches: files,
    })
    // Unambiguous match completes fully.
    expect(completeWord('cat mai', 7, files)).toEqual({
      command: 'cat main.py',
      caret: 11,
      matches: ['main.py'],
    })
    // Nothing to complete on an empty word or a dead end.
    expect(completeWord('cat ', 4, files).matches).toEqual([])
    expect(completeWord('cat xyz', 7, files).matches).toEqual([])
  })

  it('lists candidates when a Tab completion is ambiguous', () => {
    const onCandidates = vi.fn()
    const onCommandChange = vi.fn()
    setup({ command: 'cat m', onCommandChange, onCandidates })
    const input = screen.getByLabelText('Terminal command')

    fireEvent.keyDown(input, { key: 'Tab' })
    expect(onCandidates).toHaveBeenCalledWith(['main.py', 'manifest.json'])
    expect(onCommandChange).toHaveBeenCalledWith('cat ma')
  })

  it('strips escape codes and collapses carriage-return redraws', () => {
    expect(sanitizeTerminalText('installing \x1b[2K\u001b[?25hpip')).toBe('installing pip')
    expect(sanitizeTerminalText('10%\n20%\r100%\n')).toBe('10%\n100%')
    expect(makeTerminalLine('stdout', 'a\r\nb').text).toBe('a\nb')
  })
})
