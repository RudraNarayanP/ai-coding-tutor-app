import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { enqueueMiss, gradeExercise } from './grade'
import { LessonPlayer } from './LessonPlayer'
import { flipNotLesson, ghostGobbleLesson, playerLessons } from './lessons'
import { loadProgress } from './progressStore'

describe('authored boolean lessons', () => {
  it('keeps the editor off the first five screens and authors three hints', () => {
    for (const lesson of Object.values(playerLessons)) {
      expect(lesson.screens.length).toBeGreaterThanOrEqual(8)
      lesson.screens.slice(0, 5).forEach((screen) => {
        expect(screen.type).not.toBe('write_code')
      })
      lesson.screens.forEach((screen) => {
        expect(screen.hints).toHaveLength(3)
        expect(screen.explanation.length).toBeGreaterThan(0)
        const blob = JSON.stringify(screen)
        expect(blob).not.toContain('`')
      })
      const writes = lesson.screens.filter((screen) => screen.type === 'write_code')
      expect(writes.length).toBeLessThanOrEqual(2)
    }
  })

  it('grades the flip-it answers', () => {
    const [teach, mcq, predict, tap, fill, bug, predict2] = flipNotLesson.screens
    expect(gradeExercise(teach, null)).toBe(true)
    expect(gradeExercise(mcq, 'False')).toBe(true)
    expect(gradeExercise(mcq, 'True')).toBe(false)
    expect(gradeExercise(predict, 'True')).toBe(true)
    expect(gradeExercise(tap, ['keep_playing', '=', 'not', 'is_game_over'])).toBe(true)
    expect(gradeExercise(tap, ['keep_playing', '=', 'and', 'is_game_over'])).toBe(false)
    expect(gradeExercise(fill, 'not')).toBe(true)
    expect(gradeExercise(bug, '2')).toBe(true)
    expect(gradeExercise(predict2, 'True')).toBe(true)
  })

  it('re-queues a miss once', () => {
    const first = enqueueMiss(flipNotLesson.screens, flipNotLesson.screens[1], [])
    expect(first.queue.at(-1)?.id).toBe('not-mcq')
    const again = enqueueMiss(first.queue, flipNotLesson.screens[1], first.requeued)
    expect(again.queue.filter((screen) => screen.id === 'not-mcq')).toHaveLength(2)
  })

  it('ghost gobble ends on one write screen for eat_ghost', () => {
    const write = ghostGobbleLesson.screens.at(-1)
    expect(write?.type).toBe('write_code')
    expect(write?.starter).toContain('def eat_ghost')
    expect(write?.tests).toHaveLength(4)
    expect(ghostGobbleLesson.screens.filter((screen) => screen.type === 'teach')).toHaveLength(2)
  })
})

describe('LessonPlayer shell', () => {
  it('shows continue first, then a check that stays disabled until an answer', async () => {
    const user = userEvent.setup()
    localStorage.clear()
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, json: () => Promise.resolve({}) })))
    render(
      <LessonPlayer lesson={flipNotLesson} soundEnabled={false} onToggleSound={() => {}} onQuit={() => {}} />
    )

    expect(screen.queryByRole('textbox', { name: 'Code editor' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Continue' }))

    const check = screen.getByRole('button', { name: 'Check' })
    expect(check).toBeDisabled()
    await user.click(screen.getByRole('button', { name: /False/ }))
    expect(check).toBeEnabled()
    await user.click(check)
    expect(screen.getByText(/Nice!/)).toBeInTheDocument()
    expect(screen.getByText(/\+10 XP/)).toBeInTheDocument()
  })

  it('shows the authored hint ladder when Ollama is off and charges a heart for the solution', async () => {
    const user = userEvent.setup()
    localStorage.clear()
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new Error('offline')))
    )
    render(
      <LessonPlayer lesson={flipNotLesson} soundEnabled={false} onToggleSound={() => {}} onQuit={() => {}} />
    )
    await user.click(screen.getByRole('button', { name: 'Continue' }))
    const hint = screen.getByRole('button', { name: /Hint/ })
    await user.click(hint)
    expect(screen.getByText('Think of a light switch.')).toBeInTheDocument()
    await user.click(hint)
    expect(screen.getByText(/opposite of True/)).toBeInTheDocument()
    await user.click(hint)
    expect(document.querySelector('.lp-hint-text')?.textContent).toBe('False')
    expect(loadProgress().hearts).toBe(4)
    expect(screen.queryByRole('button', { name: /AI tutor unavailable/i })).not.toBeInTheDocument()
  })

  it('re-queues a wrong answer and does not show a stack trace', async () => {
    const user = userEvent.setup()
    localStorage.clear()
    render(
      <LessonPlayer lesson={flipNotLesson} soundEnabled={false} onToggleSound={() => {}} onQuit={() => {}} />
    )
    await user.click(screen.getByRole('button', { name: 'Continue' }))
    await user.click(screen.getByRole('button', { name: 'True' }))
    await user.click(screen.getByRole('button', { name: 'Check' }))
    expect(screen.getByText('Not quite.')).toBeInTheDocument()
    expect(screen.getByText(/Correct answer/)).toBeInTheDocument()
    expect(screen.queryByText(/Traceback/)).not.toBeInTheDocument()
    expect(loadProgress().hearts).toBe(4)
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    expect(screen.getByText(/What does this print/)).toBeInTheDocument()
  })
})
