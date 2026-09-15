import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { ProjectTerminal, makeTerminalLine } from './ProjectTerminal'

describe('ProjectTerminal', () => {
  it('types on the live prompt line like a VS Code terminal', () => {
    const onSubmit = vi.fn()
    const onChange = vi.fn()
    render(
      <ProjectTerminal
        cwd="/workspace"
        lines={[
          makeTerminalLine('command', 'student@patchwork:~$ ls'),
          makeTerminalLine('stdout', 'main.py'),
        ]}
        command="pip install requests"
        running={false}
        height={220}
        onCommandChange={onChange}
        onSubmit={onSubmit}
        onRunProject={() => {}}
        onClear={() => {}}
        onHistory={() => {}}
        onResizeStart={() => {}}
      />
    )

    expect(screen.getByText('Terminal')).toBeInTheDocument()
    expect(screen.getByText('1: bash')).toBeInTheDocument()
    const input = screen.getByLabelText('Terminal command') as HTMLInputElement
    expect(input.value).toBe('pip install requests')
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onSubmit).toHaveBeenCalled()
  })
})
