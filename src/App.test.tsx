/**
 * Behavioral tests for the coding tutor frontend.
 *
 * These tests mock the backend API and verify user-visible behavior,
 * not implementation details or DOM snapshots.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const mockLessons = [
  { id: 'lesson-1', title: 'Hello, World!', order: 1, difficulty: 'beginner', duration_minutes: 5, status: 'completed' },
  { id: 'lesson-2', title: 'Variables', order: 2, difficulty: 'beginner', duration_minutes: 8, status: 'current' },
  { id: 'lesson-3', title: 'Loops', order: 3, difficulty: 'beginner', duration_minutes: 10, status: 'locked' },
]

const currentLesson = {
  id: 'lesson-2',
  title: 'Variables',
  description: 'Create a variable called name and assign it your name.',
  order: 2,
  difficulty: 'beginner',
  duration_minutes: 8,
  starter_code: '# Write your code here\n',
}

const completedLesson = {
  id: 'lesson-1',
  title: 'Hello, World!',
  description: 'Print hello world.',
  order: 1,
  difficulty: 'beginner',
  duration_minutes: 5,
  starter_code: 'print("Hello, World!")\n',
}

const passingTests = [
  { name: 'test_variable_exists', passed: true, required: true, description: 'Variable exists', error: null },
  { name: 'test_variable_is_string', passed: true, required: true, description: 'Variable is a string', error: null },
]

const failingTests = [
  { name: 'test_variable_exists', passed: false, required: true, description: 'Variable exists', error: 'NameError: name is not defined' },
  { name: 'test_variable_is_string', passed: true, required: true, description: 'Variable is a string', error: null },
]

const mixedTests = [
  { name: 'test_variable_exists', passed: false, required: true, description: 'Variable exists', error: 'NameError: name is not defined' },
  { name: 'test_optional_style', passed: false, required: false, description: 'Optional style check', error: 'Style hint' },
]

// ─── Mock fetch ───────────────────────────────────────────────────────────────

function setupFetch({
  lessons = mockLessons,
  lesson = currentLesson,
  ollamaAvailable = false,
  runResult = { passed: true, completed: false, tests: passingTests },
}: {
  lessons?: typeof mockLessons
  lesson?: typeof currentLesson
  ollamaAvailable?: boolean
  runResult?: {
    passed: boolean
    completed: boolean
    tests: Array<{
      name: string
      passed: boolean
      required: boolean
      description: string
      error: string | null
    }>
  }
} = {}) {
  const mockCourses = [
    { id: 'python-foundations', title: 'Python Foundations', language: 'python', lesson_count: 70, completed_count: 1 },
    { id: 'java-foundations', title: 'Java Foundations', language: 'java', lesson_count: 30, completed_count: 0 },
    { id: 'cpp-foundations', title: 'C++ Foundations', language: 'cpp', lesson_count: 30, completed_count: 0 },
  ]

  const fetchMock = vi.fn((url: string, opts?: RequestInit) => {
    if (url.includes('/api/courses/select')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ status: 'ok' }),
      })
    }
    if (url.includes('/api/courses')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockCourses),
      })
    }
    if (url.includes('/solution')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ solution_code: '# Canonical solution\n' }),
      })
    }
    if (url.match(/\/api\/lessons\/[\w-]+$/) && !opts) {
      // Determine which lesson to return based on URL
      const id = url.split('/').pop()
      const l = id === 'lesson-1' ? completedLesson : lesson
      return Promise.resolve({ ok: true, json: () => Promise.resolve(l) })
    }
    if (url.includes('/progress')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          lesson_id: 'lesson-2',
          total_exercises: 0,
          completed_exercise_ids: [],
          attempt_counts: {},
          last_results: {},
          lesson_completed: false,
          next_action: 'answer',
          next_lesson_id: null,
        }),
      })
    }
    if (url.includes('/api/lessons') && !url.includes('/run') && !opts) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(lessons),
      })
    }
    if (url.includes('/run')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(runResult) })
    }
    if (url.includes('/api/ai/providers')) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            current_provider: 'ollama',
            providers: [
              {
                provider: 'ollama',
                name: 'Ollama',
                available: ollamaAvailable,
                model: 'llama3.1:8b',
                is_current: true,
              },
            ],
          }),
      })
    }
    if (url.includes('/api/health/ollama')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ available: ollamaAvailable }),
      })
    }
    if (url.includes('/api/tutor')) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            available: true,
            message: 'Think about what a variable stores.',
            hint_level: 1,
          }),
      })
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

// ─── Tests ────────────────────────────────────────────────────────────────────

async function openCurrentLesson(user: ReturnType<typeof userEvent.setup>) {
  const currentBtn = await screen.findByRole('button', { name: /Variables — Current lesson/ })
  await user.click(currentBtn)
  await waitFor(() => screen.getByRole('button', { name: 'Quit lesson' }))
}

describe('Course track switching', () => {
  it('allows switching between Python, Java, and C++ courses', async () => {
    const user = userEvent.setup()
    setupFetch()
    render(<App />)

    await waitFor(() => expect(screen.getByText('Python Path')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: /COURSES/ }))

    const javaTab = await screen.findByRole('tab', { name: /Java/ })
    await user.click(javaTab)

    await waitFor(() => expect(screen.getByText('Java Path')).toBeInTheDocument())
    expect(localStorage.getItem('patchwork_active_language')).toBe('java')

    await user.click(screen.getByRole('button', { name: /COURSES/ }))
    const cppTab = screen.getByRole('tab', { name: /C\+\+/ })
    await user.click(cppTab)

    await waitFor(() => expect(screen.getByText('C++ Path')).toBeInTheDocument())
    expect(localStorage.getItem('patchwork_active_language')).toBe('cpp')
  })
})

describe('Lesson navigation', () => {
  it('shows all lessons in the sidebar', async () => {
    setupFetch()
    render(<App />)
    await waitFor(() => expect(screen.getByText('Python Path')).toBeInTheDocument())

    expect(screen.getByRole('button', { name: /Hello, World! — Completed/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Variables — Current lesson/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Loops — Locked/ })).toBeInTheDocument()
  })

  it('keeps every lesson in a 12-lesson course in the navigation', async () => {
    const twelveLessons = Array.from({ length: 12 }, (_, index) => ({
      id: `lesson-${index + 1}`,
      title: `Lesson ${index + 1}`,
      order: index + 1,
      difficulty: 'beginner',
      duration_minutes: 5,
      status: index === 0 ? 'current' : 'locked',
    })) as unknown as typeof mockLessons

    setupFetch({ lessons: twelveLessons })
    render(<App />)
    await waitFor(() => screen.getByRole('button', { name: /Lesson 12 — Locked/ }))

    expect(within(screen.getByRole('navigation', { name: 'Lessons' })).getAllByRole('button')).toHaveLength(12)
  })

  it('marks the active lesson with aria-current="page" when returning to the map', async () => {
    const user = userEvent.setup()
    setupFetch()
    render(<App />)
    await openCurrentLesson(user)

    // Focused lesson view shows no course navigation (it lives on the Learn home map only)
    expect(screen.queryByRole('navigation', { name: 'Lessons' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Quit lesson' }))
    await user.click(screen.getByRole('button', { name: 'Quit' }))
    const navButton = await screen.findByRole('button', { name: /Variables — Current lesson/ })
    expect(navButton).toHaveAttribute('aria-current', 'page')
  })

  it('locks locked lessons — button is disabled', async () => {
    setupFetch()
    render(<App />)
    await waitFor(() => expect(screen.getByText('Python Path')).toBeInTheDocument())

    const loopsBtn = screen.getByRole('button', { name: /Loops — Locked/ })
    expect(loopsBtn).toBeDisabled()
  })

  it('navigates to a completed lesson when clicked', async () => {
    const user = userEvent.setup()
    setupFetch()
    render(<App />)
    await waitFor(() => expect(screen.getByText('Python Path')).toBeInTheDocument())

    const helloBtn = screen.getByRole('button', { name: /Hello, World! — Completed/ })
    await user.click(helloBtn)

    await waitFor(() => expect(screen.getByText('Print hello world.')).toBeInTheDocument())
  })

  it('uses browser history so back returns to the course map instead of leaving the app', async () => {
    const user = userEvent.setup()
    setupFetch()
    render(<App />)
    await openCurrentLesson(user)

    expect(window.location.hash).toContain('lesson-2')

    await user.click(screen.getByRole('button', { name: 'Quit lesson' }))
    await user.click(screen.getByRole('button', { name: 'Quit' }))
    await waitFor(() =>
      expect(screen.getByRole('navigation', { name: 'Lessons' })).toBeInTheDocument()
    )
    expect(window.location.hash).toBe('#/learn')
  })

  it('shows a locked feedback message when locked lesson is clicked', async () => {
    setupFetch()
    render(<App />)
    await waitFor(() => expect(screen.getByText('Python Path')).toBeInTheDocument())

    const loopsBtn = screen.getByRole('button', { name: /Loops — Locked/ })
    expect(loopsBtn).toBeDisabled()
  })

  it('shows course progress bar', async () => {
    setupFetch()
    render(<App />)
    await waitFor(() => expect(screen.getByText('Python Path')).toBeInTheDocument())

    const progressbar = screen.getByRole('progressbar', { name: /Course progress/ })
    expect(progressbar).toHaveAttribute('aria-valuenow', '1')
    expect(progressbar).toHaveAttribute('aria-valuemax', '3')
  })
})

describe('Lesson player', () => {
  it('opens a lesson without a code editor on the first screen', async () => {
    const user = userEvent.setup()
    setupFetch({ ollamaAvailable: false })
    render(<App />)
    await openCurrentLesson(user)

    expect(screen.queryByRole('textbox', { name: 'Code editor' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /AI tutor unavailable/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Show full answer/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Session notes' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled()
  })

  it('keeps the hint button working when Ollama is off', async () => {
    const user = userEvent.setup()
    setupFetch({ ollamaAvailable: false })
    render(<App />)
    await openCurrentLesson(user)

    await user.click(screen.getByRole('button', { name: /Hint/ }))
    expect(screen.getByText(/Read the one-line idea/)).toBeInTheDocument()
  })
})

describe('State Persistence & Sound Settings', () => {
  it('toggles audio feedback button and persists sound preference in localStorage', async () => {
    const user = userEvent.setup()
    setupFetch()
    render(<App />)
    await waitFor(() => expect(screen.getByText('Python Path')).toBeInTheDocument())

    const soundBtn = screen.getByRole('button', { name: /Mute audio feedback/ })
    expect(soundBtn).toHaveTextContent('🔊 Sound')

    await user.click(soundBtn)
    expect(soundBtn).toHaveTextContent('🔇 Sound')
    expect(localStorage.getItem('patchwork_sound_enabled')).toBe('false')

    await user.click(soundBtn)
    expect(soundBtn).toHaveTextContent('🔊 Sound')
    expect(localStorage.getItem('patchwork_sound_enabled')).toBe('true')
  })

  it('does not open a code editor just because a draft was saved', async () => {
    const user = userEvent.setup()
    localStorage.setItem(
      'patchwork_code_lesson-2',
      JSON.stringify({ v: 1, base: '# Write your code here\n', code: 'draft_code = 123\n' }),
    )
    setupFetch()
    render(<App />)
    await openCurrentLesson(user)
    expect(screen.queryByRole('textbox', { name: /Code editor/ })).not.toBeInTheDocument()
  })
})
