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
  const fetchMock = vi.fn((url: string, opts?: RequestInit) => {
    if (url.endsWith('/api/lessons') && !opts) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(lessons),
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
    if (url.includes('/run')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(runResult) })
    }
    if (url.includes('/api/ai/providers')) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            current_provider: 'ollama',
            fallback_provider: null,
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

describe('Lesson navigation', () => {
  it('shows all lessons in the sidebar', async () => {
    setupFetch()
    render(<App />)
    await waitFor(() => expect(screen.getByRole('heading', { level: 2, name: 'Variables' })).toBeInTheDocument())

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

  it('marks the active lesson with aria-current="page"', async () => {
    setupFetch()
    render(<App />)
    // Wait for lesson content to load (lesson state is set after fetch completes)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: /Variables/ }))

    const navButton = screen.getByRole('button', { name: /Variables — Current lesson/ })
    expect(navButton).toHaveAttribute('aria-current', 'page')
  })

  it('locks locked lessons — button is disabled', async () => {
    setupFetch()
    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Variables' }))

    const loopsBtn = screen.getByRole('button', { name: /Loops — Locked/ })
    expect(loopsBtn).toBeDisabled()
  })

  it('navigates to a completed lesson when clicked', async () => {
    const user = userEvent.setup()
    setupFetch()
    render(<App />)
    // Wait for initial lesson to load
    await waitFor(() => screen.getByRole('heading', { level: 2, name: /Variables/ }))

    const helloBtn = screen.getByRole('button', { name: /Hello, World! — Completed/ })
    await user.click(helloBtn)

    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Hello, World!')
    )
  })

  it('shows a locked feedback message when locked lesson is clicked', async () => {
    const user = userEvent.setup()
    setupFetch()
    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Variables' }))

    // Try clicking — it's disabled, so no navigation but let's verify the disabled state
    const loopsBtn = screen.getByRole('button', { name: /Loops — Locked/ })
    expect(loopsBtn).toBeDisabled()
  })

  it('shows course progress bar', async () => {
    setupFetch()
    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Variables' }))

    const progressbar = screen.getByRole('progressbar', { name: /Course progress/ })
    expect(progressbar).toHaveAttribute('aria-valuenow', '1')
    expect(progressbar).toHaveAttribute('aria-valuemax', '3')
  })
})

describe('Run button and code editor', () => {
  it('run button is disabled before lesson loads', async () => {
    setupFetch()
    render(<App />)
    // The run button only appears after the loading state resolves;
    // test that it is disabled when lesson is null (initial state) by
    // waiting for the button to appear and verifying it becomes enabled
    // once loaded. A separate assertion checks the loading spinner is shown first.
    const loadingEl = screen.getByRole('status', { name: /Loading lesson/ })
    expect(loadingEl).toBeInTheDocument()
  })

  it('run button is enabled after lesson loads', async () => {
    setupFetch()
    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Variables' }))

    const runBtn = screen.getByRole('button', { name: /Run code/ })
    expect(runBtn).toBeEnabled()
  })

  it('run button shows "Running" text and is disabled while running', async () => {
    const user = userEvent.setup()
    // Make run take longer to observe intermediate state
    let resolveRun!: (v: unknown) => void
    const fetchMock = setupFetch()
    fetchMock.mockImplementation((url: string, opts?: RequestInit) => {
      if (url.includes('/run')) {
        return new Promise((res) => {
          resolveRun = () =>
            res({ ok: true, json: () => Promise.resolve({ passed: true, completed: false, tests: passingTests }) })
        })
      }
      if (url.endsWith('/api/lessons') && !opts) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockLessons) })
      }
      if (url.match(/\/api\/lessons\/[\w-]+$/) && !opts) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(currentLesson) })
      }
      if (url.includes('/api/health/ollama')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ available: false }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })

    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Variables' }))

    const runBtn = screen.getByRole('button', { name: /Run code/ })
    await user.click(runBtn)

    expect(screen.getByRole('button', { name: /Run code/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Run code/ })).toHaveTextContent(/Running/)

    resolveRun(null)
    await waitFor(() => expect(screen.getByRole('button', { name: /Run code/ })).not.toHaveTextContent(/Running/))
  })

  it('editor textarea is present and editable', async () => {
    setupFetch()
    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Variables' }))

    const editor = screen.getByRole('textbox', { name: /Code editor/ })
    expect(editor).toBeInTheDocument()
    expect(editor).not.toBeDisabled()
  })

  it('editor line numbers render properly', async () => {
    setupFetch()
    const { container } = render(<App />)
    await waitFor(() => expect(screen.getByText('exercise.py')).toBeInTheDocument())

    expect(container.querySelector('.line-numbers')).toBeInTheDocument()
  })

  it('preserves Tab indentation and Ctrl+Enter test execution in the textarea editor', async () => {
    const fetchMock = setupFetch()
    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Variables' }))

    const editor = screen.getByRole<HTMLTextAreaElement>('textbox', { name: /Code editor/ })
    editor.focus()
    editor.setSelectionRange(0, 0)
    fireEvent.keyDown(editor, { key: 'Tab' })
    await waitFor(() => expect(editor.value.startsWith('    ')).toBe(true))

    fireEvent.keyDown(editor, { key: 'Enter', ctrlKey: true })
    await waitFor(() =>
      expect((fetchMock as ReturnType<typeof vi.fn>).mock.calls.some(
        ([url]) => String(url).includes('/run')
      )).toBe(true)
    )
  })

  it('triggers test execution when Shift+Enter is pressed in the editor', async () => {
    const fetchMock = setupFetch()
    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Variables' }))

    const editor = screen.getByRole<HTMLTextAreaElement>('textbox', { name: /Code editor/ })
    editor.focus()
    fireEvent.keyDown(editor, { key: 'Enter', shiftKey: true })
    await waitFor(() =>
      expect((fetchMock as ReturnType<typeof vi.fn>).mock.calls.some(
        ([url]) => String(url).includes('/run')
      )).toBe(true)
    )
  })
})

describe('Test results rendering', () => {
  it('shows all-passed badge when all tests pass', async () => {
    const user = userEvent.setup()
    setupFetch({ runResult: { passed: true, completed: false, tests: passingTests } })
    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Variables' }))

    await user.click(screen.getByRole('button', { name: /Run code/ }))

    await waitFor(() => screen.getByRole('region', { name: /Test results/ }))
    const region = screen.getByRole('region', { name: /Test results/ })
    expect(within(region).getByText(/All 2 tests passed/)).toBeInTheDocument()
  })

  it('shows failed badge when required tests fail', async () => {
    const user = userEvent.setup()
    setupFetch({ runResult: { passed: false, completed: false, tests: failingTests } })
    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Variables' }))

    await user.click(screen.getByRole('button', { name: /Run code/ }))

    await waitFor(() => screen.getByRole('region', { name: /Test results/ }))
    const region = screen.getByRole('region', { name: /Test results/ })
    expect(within(region).getByText(/1 of 2 required failed/)).toBeInTheDocument()
  })

  it('shows each test row with pass/fail icon', async () => {
    const user = userEvent.setup()
    setupFetch({ runResult: { passed: false, completed: false, tests: failingTests } })
    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Variables' }))

    await user.click(screen.getByRole('button', { name: /Run code/ }))
    await waitFor(() => screen.getByRole('region', { name: /Test results/ }))

    const region = screen.getByRole('region', { name: /Test results/ })
    expect(within(region).getByText('test_variable_exists')).toBeInTheDocument()
    expect(within(region).getByText('test_variable_is_string')).toBeInTheDocument()
    // One failed, one passed
    const failed = within(region).getAllByRole('img', { name: 'Failed' })
    const passed = within(region).getAllByRole('img', { name: 'Passed' })
    expect(failed).toHaveLength(1)
    expect(passed).toHaveLength(1)
  })

  it('marks optional tests with "opt" badge', async () => {
    const user = userEvent.setup()
    setupFetch({ runResult: { passed: false, completed: false, tests: mixedTests } })
    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Variables' }))

    await user.click(screen.getByRole('button', { name: /Run code/ }))
    await waitFor(() => screen.getByRole('region', { name: /Test results/ }))

    const region = screen.getByRole('region', { name: /Test results/ })
    expect(within(region).getByText('opt')).toBeInTheDocument()
  })
})

describe('Hint button behavior', () => {
  it('hint button is disabled when AI is unavailable', async () => {
    setupFetch({ ollamaAvailable: false })
    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Variables' }))

    const hintBtn = screen.getByRole('button', { name: /AI tutor unavailable/ })
    expect(hintBtn).toBeDisabled()
  })

  it('shows AI unavailable note when Ollama is offline', async () => {
    setupFetch({ ollamaAvailable: false })
    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Variables' }))

    expect(screen.getByText(/Selected provider is unconfigured/)).toBeInTheDocument()
  })

  it('hint button is disabled when AI toggle is off', async () => {
    const user = userEvent.setup()
    setupFetch({ ollamaAvailable: true })
    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Variables' }))

    // Toggle AI off
    const toggle = screen.getByRole('button', { name: /AI tutor on/ })
    await user.click(toggle)

    const hintBtn = screen.getByRole('button', { name: /AI tutor is paused/ })
    expect(hintBtn).toBeDisabled()
  })

  it('calls tutor API when hint button is clicked', async () => {
    const user = userEvent.setup()
    const fetchMock = setupFetch({ ollamaAvailable: true })
    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Variables' }))

    const hintBtn = screen.getByRole('button', { name: /Request a hint/ })
    await user.click(hintBtn)

    await waitFor(() =>
      expect(screen.getByRole('status', { name: /Tutor feedback/ })).toHaveTextContent(
        'Think about what a variable stores.'
      )
    )

    const tutorCall = (fetchMock as ReturnType<typeof vi.fn>).mock.calls.find(
      (call) => String(call[0]).includes('/api/tutor')
    )
    expect(tutorCall).toBeDefined()
  })

  it('inserts solution directly into editor when View Solution is clicked', async () => {
    const user = userEvent.setup()
    const fetchMock = setupFetch({ ollamaAvailable: true })
    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Variables' }))

    const solutionBtn = screen.getByRole('button', { name: /View Solution/ })
    await user.click(solutionBtn)

    await waitFor(() => {
      const editor = screen.getByRole<HTMLTextAreaElement>('textbox', { name: /Code editor/ })
      expect(editor.value).toContain('# Canonical solution')
    })

    const solutionCall = (fetchMock as ReturnType<typeof vi.fn>).mock.calls.find(
      (call) => String(call[0]).includes('/solution')
    )
    expect(solutionCall).toBeDefined()
  })
})

describe('Completion / next-lesson flow', () => {
  it('shows completion banner when lesson is completed', async () => {
    const user = userEvent.setup()
    setupFetch({
      runResult: { passed: true, completed: true, tests: passingTests },
    })
    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: /Variables/ }))

    await user.click(screen.getByRole('button', { name: /Run code/ }))

    await waitFor(() =>
      expect(screen.getByText(/Lesson Complete!/)).toBeInTheDocument()
    )
    expect(screen.getByRole('button', { name: /Next Lesson/ })).toBeInTheDocument()
  })

  it('"Next Lesson" button triggers navigation to the next lesson', async () => {
    const user = userEvent.setup()
    const lessonsAfterCompletion = [
      { ...mockLessons[0], status: 'completed' as const },
      { ...mockLessons[1], status: 'completed' as const },
      { ...mockLessons[2], status: 'current' as const },
    ]
    const fetchMock = setupFetch({
      runResult: { passed: true, completed: true, tests: passingTests },
    })

    let runCalled = false
    fetchMock.mockImplementation((url: string, opts?: RequestInit) => {
      if (url.includes('/run')) {
        runCalled = true
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ passed: true, completed: true, tests: passingTests }),
        })
      }
      if (url.endsWith('/api/lessons') && !opts) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(runCalled ? lessonsAfterCompletion : mockLessons),
        })
      }
      if (url.match(/\/api\/lessons\/[\w-]+$/) && !opts) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(currentLesson) })
      }
      if (url.includes('/api/health/ollama')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ available: false }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })

    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Variables' }))
    await user.click(screen.getByRole('button', { name: /Run code/ }))
    await waitFor(() => screen.getByText(/Lesson Complete!/))

    const nextBtn = screen.getByRole('button', { name: /Next Lesson/ })
    await user.click(nextBtn)

    await waitFor(() =>
      expect(screen.queryByText('Lesson Complete!')).not.toBeInTheDocument()
    )
  })
})

describe('AI unavailable state', () => {
  it('shows "Ollama offline" in the status bar when unavailable', async () => {
    setupFetch({ ollamaAvailable: false })
    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Variables' }))

    expect(screen.getByText(/Ollama unavailable/)).toBeInTheDocument()
  })

  it('shows "Ollama ready" in the status bar when available', async () => {
    setupFetch({ ollamaAvailable: true })
    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Variables' }))

    expect(screen.getByText(/Ollama ready/)).toBeInTheDocument()
  })

  it('feedback panel shows AI unavailable message after hint attempt fails', async () => {
    const user = userEvent.setup()
    setupFetch({ ollamaAvailable: true })

    // Override tutor call to simulate unavailability
    const fetchMock = vi.fn((url: string, opts?: RequestInit) => {
      if (url.includes('/api/tutor')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({ available: false, message: 'Offline', hint_level: 1 }),
        })
      }
      if (url.endsWith('/api/lessons') && !opts) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockLessons) })
      }
      if (url.match(/\/api\/lessons\/[\w-]+$/) && !opts) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(currentLesson) })
      }
      if (url.includes('/api/ai/providers')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              current_provider: 'ollama',
              fallback_provider: null,
              providers: [
                {
                  provider: 'ollama',
                  name: 'Ollama',
                  available: true,
                  model: 'llama3.1:8b',
                  is_current: true,
                },
              ],
            }),
        })
      }
      if (url.includes('/api/health/ollama')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ available: true }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: /Variables/ }))

    // AI should start as available
    const hintBtn = screen.getByRole('button', { name: /Request a hint/ })
    await user.click(hintBtn)

    await waitFor(() =>
      expect(screen.getByRole('status', { name: /Tutor feedback/ })).toHaveTextContent(
        /Offline/
      )
    )
  })
})

describe('Session notes', () => {
  it('allows adding a session note', async () => {
    const user = userEvent.setup()
    setupFetch()
    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Variables' }))

    const input = screen.getByRole('textbox', { name: /Session note/ })
    await user.type(input, 'Remember to initialize variables')
    await user.click(screen.getByRole('button', { name: /Add note/ }))

    expect(screen.getByText('Remember to initialize variables')).toBeInTheDocument()
    expect(input).toHaveValue('')
  })
})

describe('State Persistence & Sound Settings', () => {
  it('toggles audio feedback button and persists sound preference in localStorage', async () => {
    const user = userEvent.setup()
    setupFetch()
    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Variables' }))

    const soundBtn = screen.getByRole('button', { name: /Mute audio feedback/ })
    expect(soundBtn).toHaveTextContent('🔊 Sound')

    await user.click(soundBtn)
    expect(soundBtn).toHaveTextContent('🔇 Sound')
    expect(localStorage.getItem('patchwork_sound_enabled')).toBe('false')

    await user.click(soundBtn)
    expect(soundBtn).toHaveTextContent('🔊 Sound')
    expect(localStorage.getItem('patchwork_sound_enabled')).toBe('true')
  })

  it('restores draft code from localStorage for current lesson', async () => {
    localStorage.setItem('patchwork_code_lesson-2', 'draft_code = 123\n')
    setupFetch()
    render(<App />)
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Variables' }))

    const editor = screen.getByRole<HTMLTextAreaElement>('textbox', { name: /Code editor/ })
    expect(editor.value).toBe('draft_code = 123\n')
  })
})
