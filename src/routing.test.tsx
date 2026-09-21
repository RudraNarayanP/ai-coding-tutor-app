/**
 * Routing tests: the URL is the navigation state, so these assert on
 * `window.location` and on real history movement rather than on internal state.
 *
 * jsdom implements pushState, popstate and history.go(), so Back and Forward are
 * driven the way a user drives them — no mocked navigator.
 */

import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

import { setupFetch } from './routingFixtures'

const at = () => window.location.pathname
const goto = (path: string) => window.history.replaceState(null, '', path)
const back = () => window.history.go(-1)
const forward = () => window.history.go(1)

beforeEach(() => {
  localStorage.clear()
  goto('/learn')
  setupFetch()
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('Route rendering', () => {
  it('sends the bare root to the learning map without spending a history entry', async () => {
    goto('/')
    const lengthBefore = window.history.length
    render(<App />)

    await screen.findByRole('button', { name: /Variables — Current lesson/ })
    expect(at()).toBe('/learn')
    expect(window.history.length).toBe(lengthBefore)
  })

  it('renders every major screen at its own address', async () => {
    const routes: [string, RegExp][] = [
      ['/courses', /Python Foundations/],
      ['/practice', /Rewind|Practice|Guidebook/i],
      ['/quests', /Quests|Daily/i],
      ['/leaderboards', /Leaderboard/],
      ['/profile', /Rudra/],
      ['/create', /Create|guided/i],
    ]
    for (const [path, pattern] of routes) {
      goto(path)
      const { unmount } = render(<App />)
      await waitFor(() =>
        expect(document.body.textContent).toMatch(pattern),
        { timeout: 3000 },
      )
      expect(at()).toBe(path)
      unmount()
      cleanup()
    }
  })
})

describe('Navigation through the hierarchy', () => {
  /**
   * Answer the step currently on screen and let the app move on. Re-querying at
   * the last moment matters: a graded step replaces itself, so a handle grabbed
   * earlier can point at a node that is already gone.
   */
  async function answerAndSubmit(user: ReturnType<typeof userEvent.setup>, option: RegExp) {
    await user.click(await screen.findByRole('button', { name: option }))
    await user.click(await screen.findByRole('button', { name: /^SUBMIT$/ }))
  }

  it('map → course → unit → lesson → step each change the URL', async () => {
    const user = userEvent.setup()
    render(<App />)

    // The header pill is the way to the course list.
    await user.click(await screen.findByRole('button', { name: 'Open courses' }))
    await waitFor(() => expect(at()).toBe('/courses'))

    await user.click(await screen.findByRole('tab', { name: /Python/ }))
    await waitFor(() => expect(at()).toBe('/course/python-foundations'))

    // The unit banner is the way down a level.
    await user.click(await screen.findByRole('button', { name: /Open Unit 1: Talking to the Computer/ }))
    await waitFor(() => expect(at()).toBe('/course/python-foundations/unit/unit-basics'))

    // Inside the unit only that unit's lessons are listed.
    expect(screen.getByRole('button', { name: /Variables — Current lesson/ })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Variables — Current lesson/ }))
    await waitFor(() => expect(at()).toBe('/lesson/lesson-2'))
    await screen.findByText('Which line stores a value?')

    // Opening a lesson lands on step 1 without adding a step segment.
    expect(at()).not.toContain('/exercise/')

    // A correct answer is what moves a learner to the next step in this app, so
    // that is the moment that becomes a history entry.
    await answerAndSubmit(user, /name = "Ada"/)
    await waitFor(() => expect(at()).toBe('/lesson/lesson-2/exercise/ex-2'))
  })

  it('Back walks out through step → lesson → unit → course → list → map', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(await screen.findByRole('button', { name: 'Open courses' }))
    await user.click(await screen.findByRole('tab', { name: /Python/ }))
    await user.click(await screen.findByRole('button', { name: /Open Unit 1/ }))
    await user.click(await screen.findByRole('button', { name: /Variables — Current lesson/ }))
    await screen.findByText('Which line stores a value?')
    await answerAndSubmit(user, /name = "Ada"/)
    await waitFor(() => expect(at()).toBe('/lesson/lesson-2/exercise/ex-2'))

    const expected = [
      '/lesson/lesson-2',
      '/course/python-foundations/unit/unit-basics',
      '/course/python-foundations',
      '/courses',
      '/learn',
    ]
    for (const path of expected) {
      back()
      await waitFor(() => expect(at()).toBe(path), { timeout: 2000 })
    }

    // …and Forward puts the same screens back, step included. We are on /learn,
    // so the five forwards are the five screens that came after it.
    const forwards = [
      '/courses',
      '/course/python-foundations',
      '/course/python-foundations/unit/unit-basics',
      '/lesson/lesson-2',
      '/lesson/lesson-2/exercise/ex-2',
    ]
    expect(at()).toBe('/learn')
    for (const path of forwards) {
      forward()
      await waitFor(() => expect(at()).toBe(path), { timeout: 2000 })
    }
    await screen.findByText('Which one reads it back?')
  })

  it('resolves the course for the unit link when the URL does not name one', async () => {
    // `/learn` carries no course id — it uses the stored track. The unit link has
    // to be built from the resolved course, or it becomes /course/undefined/….
    const user = userEvent.setup()
    render(<App />)

    await user.click(await screen.findByRole('button', { name: /Open Unit 1: Talking to the Computer/ }))
    await waitFor(() =>
      expect(at()).toBe('/course/python-foundations/unit/unit-basics')
    )
    expect(at()).not.toContain('undefined')

    await user.click(await screen.findByRole('button', { name: /Variables — Current lesson/ }))
    await waitFor(() => expect(at()).toBe('/lesson/lesson-2'))
    await screen.findByText('Which line stores a value?')
  })

  it('does not leave the app while the app still owns history', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: 'Open courses' }))
    await waitFor(() => expect(at()).toBe('/courses'))

    back()
    await waitFor(() => expect(at()).toBe('/learn'))
    // One more Back has nothing of ours left, which is the app's own edge —
    // the point is it is reached only after our entries are used up.
    expect(window.history.state?.idx).toBe(0)
  })
})

describe('Returning to a cleared step', () => {
  it('shows it read-only with a way forward instead of a dead submit', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Variables — Current lesson/ }))
    await screen.findByText('Which line stores a value?')
    await user.click(screen.getByRole('button', { name: /name = "Ada"/ }))
    await user.click(screen.getByRole('button', { name: /^SUBMIT$/ }))
    await waitFor(() => expect(at()).toBe('/lesson/lesson-2/exercise/ex-2'))
    await user.click(await screen.findByRole('button', { name: /^print\(name\)$/ }))
    await user.click(await screen.findByRole('button', { name: /^SUBMIT$/ }))
    await waitFor(() => expect(at()).toBe('/lesson/lesson-2/exercise/ex-3'))

    // Back onto step 2, which is already graded. The URL owns which step is on
    // screen; the backend owns that it is finished — so this shows the step, says
    // it is cleared, and offers a way forward rather than a dead Submit.
    back()
    await waitFor(() => expect(at()).toBe('/lesson/lesson-2/exercise/ex-2'))
    await waitFor(() =>
      expect(document.body.textContent).toMatch(/already cleared this step/i)
    )
    expect(document.body.textContent).toContain('Which one reads it back?')
    expect(screen.queryByRole('button', { name: /^SUBMIT$/ })).not.toBeInTheDocument()

    // Continue returns the learner to where they actually stand.
    await user.click(screen.getByRole('button', { name: /Continue/i }))
    await waitFor(() => expect(at()).toBe('/lesson/lesson-2/exercise/ex-3'))
  })
})

describe('Multi-exercise lesson completion', () => {
  /**
   * Answer the step on screen and let the app move on. Returns nothing; every
   * caller asserts on the URL and the panel it expects afterwards.
   */
  async function solve(user: ReturnType<typeof userEvent.setup>, option: RegExp) {
    await user.click(await screen.findByRole('button', { name: option }))
    await user.click(await screen.findByRole('button', { name: /^SUBMIT$/ }))
    await new Promise((r) => setTimeout(r, 120))
  }

  async function openLesson(user: ReturnType<typeof userEvent.setup>) {
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Variables — Current lesson/ }))
    await waitFor(() => expect(at()).toBe('/lesson/lesson-2'))
    await screen.findByText('Which line stores a value?')
  }

  it('advances on a non-final answer without ending the lesson', async () => {
    const user = userEvent.setup()
    await openLesson(user)

    await solve(user, /name = "Ada"/)
    await waitFor(() => expect(at()).toBe('/lesson/lesson-2/exercise/ex-2'))
    expect(document.body.textContent).not.toMatch(/Lesson Complete/)
    expect(screen.queryByRole('button', { name: /Next Lesson/i })).not.toBeInTheDocument()
  })

  it('shows the completion panel after the final answer and Next Lesson walks on', async () => {
    const user = userEvent.setup()
    await openLesson(user)

    await solve(user, /name = "Ada"/)
    await solve(user, /^print\(name\)$/)
    expect(document.body.textContent).not.toMatch(/Lesson Complete/)

    await solve(user, /A value/)

    // The last answer both finishes the lesson and brings up the reward, so the
    // URL comes to rest on the lesson rather than on a step that no longer exists.
    await waitFor(() => expect(at()).toBe('/lesson/lesson-2'))
    await waitFor(() =>
      expect(document.body.textContent).toMatch(/Lesson Complete/)
    )
    expect(document.body.textContent).toMatch(/\+10 XP earned/)

    await user.click(await screen.findByRole('button', { name: /Next Lesson/i }))
    await waitFor(() => expect(at()).toBe('/lesson/lesson-3'))
    await screen.findByText('Write the code and run it.', {}, { timeout: 3000 })
  })

  it('keeps the completion panel and the URL together across Back and Forward', async () => {
    const user = userEvent.setup()
    await openLesson(user)
    await solve(user, /name = "Ada"/)
    await solve(user, /^print\(name\)$/)
    await solve(user, /A value/)
    await waitFor(() => expect(at()).toBe('/lesson/lesson-2'))
    await screen.findByText(/Lesson Complete/)

    // Back over the steps just cleared: each is read-only, none re-awards.
    back()
    await waitFor(() => expect(at()).toBe('/lesson/lesson-2/exercise/ex-2'))
    await waitFor(() => expect(document.body.textContent).toMatch(/already cleared this step/i))
    expect(screen.queryByRole('button', { name: /^SUBMIT$/ })).not.toBeInTheDocument()

    // Forward returns to the finished lesson, reward panel still on screen.
    forward()
    await waitFor(() => expect(at()).toBe('/lesson/lesson-2'))
    await screen.findByText(/Lesson Complete/)
  })

  it('keeps the completion panel and Next Lesson when returning to a finished lesson', async () => {
    const user = userEvent.setup()
    await openLesson(user)
    await solve(user, /name = "Ada"/)
    await solve(user, /^print\(name\)$/)
    await solve(user, /A value/)
    await waitFor(() => expect(at()).toBe('/lesson/lesson-2'))
    await screen.findByText(/Lesson Complete/)

    // On to the next lesson, then Back into the one just finished. The one-shot
    // celebration is long gone by then; the panel comes back because the server
    // still reports every step done — and it does not restate the XP.
    await user.click(await screen.findByRole('button', { name: /Next Lesson/i }))
    await waitFor(() => expect(at()).toBe('/lesson/lesson-3'))
    back()
    await waitFor(() => expect(at()).toBe('/lesson/lesson-2'))
    await screen.findByText(/Lesson Complete/)
    expect(document.body.textContent).not.toMatch(/\+10 XP earned/)
    await user.click(screen.getByRole('button', { name: /Next Lesson/i }))
    await waitFor(() => expect(at()).toBe('/lesson/lesson-3'))
  })

  it('does not reopen a step when a finished lesson is refreshed', async () => {
    const user = userEvent.setup()
    await openLesson(user)
    await solve(user, /name = "Ada"/)
    await solve(user, /^print\(name\)$/)
    await solve(user, /A value/)
    await waitFor(() => expect(at()).toBe('/lesson/lesson-2'))

    // A fresh mount rebuilds from the server's progress, which says everything is
    // done: no step can be re-entered and no XP can be offered twice.
    cleanup()
    render(<App />)
    await waitFor(() => expect(at()).toBe('/lesson/lesson-2'), { timeout: 3000 })
    await new Promise((r) => setTimeout(r, 400))
    expect(document.body.textContent).not.toMatch(/Which line stores a value\?/)
    expect(screen.queryByRole('button', { name: /^SUBMIT$/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Back to Map/i })).toBeInTheDocument()
  })
})

describe('Deep links', () => {  it('opens a lesson straight from its URL', async () => {
    goto('/lesson/lesson-2')
    render(<App />)

    await screen.findByText('Which line stores a value?', {}, { timeout: 3000 })
    expect(at()).toBe('/lesson/lesson-2')
  })

  it('restores a pinned step from the URL', async () => {
    goto('/lesson/lesson-2/exercise/ex-2')
    render(<App />)

    // ex-2 has not been served yet (nothing is completed), so the URL is
    // normalised onto the step the backend actually has for this learner.
    await waitFor(() => expect(at()).toBe('/lesson/lesson-2'), { timeout: 3000 })
    await screen.findByText('Which line stores a value?')
  })

  it('keeps the URL after a refresh mid-lesson', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Variables — Current lesson/ }))
    await screen.findByText('Which line stores a value?')
    await user.click(screen.getByRole('button', { name: /name = "Ada"/ }))
    await user.click(screen.getByRole('button', { name: /^SUBMIT$/ }))
    await waitFor(() => expect(at()).toBe('/lesson/lesson-2/exercise/ex-2'))

    // A refresh is a fresh mount at the same address. The mock keeps its own
    // record of what was graded, exactly as the server does: step 1 is complete,
    // so step 2 is the step this learner has actually been served.
    cleanup()
    render(<App />)
    await screen.findByText('Which one reads it back?', {}, { timeout: 3000 })
    expect(at()).toBe('/lesson/lesson-2/exercise/ex-2')
  })
})

describe('Routes that do not exist', () => {
  it('shows not-found for a lesson id the server rejects, without crashing', async () => {
    goto('/lesson/no-such-lesson')
    render(<App />)

    await waitFor(
      () => expect(document.body.textContent).toMatch(/Nothing here matches that address/),
      { timeout: 3000 },
    )
    // Still an app, not a white page: the chrome survived the bad route.
    expect(screen.getByRole('navigation', { name: 'App Navigation Tabs' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Back to my learning map/ })).toBeInTheDocument()
  })

  it('shows not-found for an unknown course and an unknown path', async () => {
    for (const path of ['/course/nope-not-a-course', '/totally/unknown']) {
      goto(path)
      render(<App />)
      await waitFor(
        () => expect(document.body.textContent).toMatch(/Nothing here matches that address/),
        { timeout: 3000 },
      )
      cleanup()
    }
  })

  it('redirects the review alias onto the mistake queue card', async () => {
    goto('/review')
    render(<App />)
    await waitFor(() => expect(at()).toBe('/practice/mistakes'), { timeout: 3000 })
  })
})

describe('Transient state stays out of history', () => {
  it('an armed answer reveal, a modal and an answer change push nothing', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Variables — Current lesson/ }))
    await screen.findByText('Which line stores a value?')

    const entries = window.history.length

    // "Show full answer" arms a two-tap reveal: pure feedback state.
    await user.click(screen.getByRole('button', { name: /Show full answer/ }))
    // The settings modal is visibility state, not a destination.
    await user.click(screen.getByRole('button', { name: '⚙️ Settings' }))
    // Picking a different option is an answer being composed.
    await user.click(screen.getByRole('button', { name: /print\(name\)/ }))

    await waitFor(() => expect(window.history.length).toBe(entries))
    expect(at()).toBe('/lesson/lesson-2')

    // And it is still the same lesson afterwards, with the URL intact.
    expect(screen.getByText('Which line stores a value?')).toBeInTheDocument()
  })
})
