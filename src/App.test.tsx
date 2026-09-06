/**
 * Behavioral tests for the coding tutor frontend.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const mockLessons = [
  { id: 'variables-01', title: 'Variable Assignment & Values', order: 1, difficulty: 'beginner', duration_minutes: 5, status: 'completed' },
  { id: 'numbers-01', title: 'Numbers & Arithmetic', order: 2, difficulty: 'beginner', duration_minutes: 8, status: 'current' },
  { id: 'expressions-01', title: 'Expressions & Evaluation', order: 3, difficulty: 'beginner', duration_minutes: 10, status: 'locked' },
]

const currentLesson = {
  id: 'numbers-01',
  title: 'Numbers & Arithmetic',
  description: 'Create a variable called age and assign it 20.',
  order: 2,
  difficulty: 'beginner',
  duration_minutes: 8,
  starter_code: '# Write code here\n',
}

const completedLesson = {
  id: 'variables-01',
  title: 'Variable Assignment & Values',
  description: 'Create a variable called country and set it to Italy.',
  order: 1,
  difficulty: 'beginner',
  duration_minutes: 5,
  starter_code: 'country = "Italy"\n',
}

const passingTests = [
  { name: 'test_age_exists', passed: true, required: true, description: 'Variable age exists', error: null },
]

const failingTests = [
  { name: 'test_age_exists', passed: false, required: true, description: 'Variable age exists', error: 'NameError: age is not defined' },
]

// ─── Mock fetch ───────────────────────────────────────────────────────────────

function setupFetch({
  lessons = mockLessons,
  lesson = currentLesson,
  ollamaAvailable = true,
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
    if (url.match(/\/api\/lessons\/[\w-]+$/) && !opts) {
      const id = url.split('/').pop()
      const l = id === 'variables-01' ? completedLesson : lesson
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
                reason: ollamaAvailable ? null : 'Selected provider is unconfigured.',
              },
            ],
          }),
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

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('Duolingo Course Map Navigation', () => {
  it('renders the Duolingo course map layout with units', async () => {
    setupFetch()
    render(<App />)
    await waitFor(() => expect(screen.getByText('Python Learning Progression')).toBeInTheDocument())
    expect(screen.getByText(/Unit 1: Python Basics & Variables/)).toBeInTheDocument()
  })

  it('allows clicking a current lesson node to open the exercise screen', async () => {
    const user = userEvent.setup()
    setupFetch()
    render(<App />)
    await waitFor(() => screen.getByText('Python Learning Progression'))

    const nodeBtn = screen.getByRole('button', { name: /Numbers & Arithmetic — Current lesson/ })
    await user.click(nodeBtn)

    await waitFor(() => expect(screen.getByRole('heading', { level: 2, name: 'Numbers & Arithmetic' })).toBeInTheDocument())
    expect(screen.getByText(/← Back to Course Path/)).toBeInTheDocument()
  })

  it('disables locked lesson nodes', async () => {
    setupFetch()
    render(<App />)
    await waitFor(() => screen.getByText('Python Learning Progression'))

    const lockedBtn = screen.getByRole('button', { name: /Expressions & Evaluation — Locked/ })
    expect(lockedBtn).toBeDisabled()
  })
})

describe('Bite-sized Exercise Screen', () => {
  it('runs tests and displays immediate feedback', async () => {
    const user = userEvent.setup()
    setupFetch({ runResult: { passed: true, completed: false, tests: passingTests } })
    render(<App />)
    await waitFor(() => screen.getByText('Python Learning Progression'))

    await user.click(screen.getByRole('button', { name: /Numbers & Arithmetic — Current lesson/ }))
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Numbers & Arithmetic' }))

    const checkBtn = screen.getByRole('button', { name: /Run code/ })
    await user.click(checkBtn)

    await waitFor(() => screen.getByRole('region', { name: /Test results/ }))
    expect(screen.getByText(/✓ All 1 checks passed!/)).toBeInTheDocument()
  })

  it('shows completion modal when exercise is completed', async () => {
    const user = userEvent.setup()
    setupFetch({ runResult: { passed: true, completed: true, tests: passingTests } })
    render(<App />)
    await waitFor(() => screen.getByText('Python Learning Progression'))

    await user.click(screen.getByRole('button', { name: /Numbers & Arithmetic — Current lesson/ }))
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Numbers & Arithmetic' }))

    await user.click(screen.getByRole('button', { name: /Run code/ }))

    await waitFor(() => screen.getByText('LESSON COMPLETE!'))
    expect(screen.getByText('+25 XP')).toBeInTheDocument()
  })

  it('calls tutor API when hint button is clicked', async () => {
    const user = userEvent.setup()
    const fetchMock = setupFetch({ ollamaAvailable: true })
    render(<App />)
    await waitFor(() => screen.getByText('Python Learning Progression'))

    await user.click(screen.getByRole('button', { name: /Numbers & Arithmetic — Current lesson/ }))
    await waitFor(() => screen.getByRole('heading', { level: 2, name: 'Numbers & Arithmetic' }))

    const hintBtn = screen.getByRole('button', { name: /Request a hint/ })
    await user.click(hintBtn)

    await waitFor(() =>
      expect(screen.getByRole('status', { name: /Tutor feedback/ })).toHaveTextContent(
        'Think about what a variable stores.'
      )
    )
  })
})
