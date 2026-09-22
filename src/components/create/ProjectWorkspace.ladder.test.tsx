/**
 * The guided-project workspace with its teaching ladder wired up.
 *
 * The original `ProjectWorkspace.test.tsx` suite passes with or without this
 * feature, because `useStepSession` reads the session over raw `fetch`, that
 * fetch is unmocked there, and the ladder correctly degrades to the plain task
 * card. So the rungs needed their own file: without it the whole feature could
 * be deleted and nothing would notice.
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ProjectWorkspace } from './ProjectWorkspace'
import { projectApi, type ProjectView } from '../../utils/projectApi'

vi.mock('../../utils/projectApi', () => ({
  projectApi: {
    get: vi.fn(),
    saveWorkspace: vi.fn(),
    run: vi.fn(),
    exec: vi.fn(),
    next: vi.fn(),
    guidance: vi.fn(),
    remove: vi.fn(),
    list: vi.fn(),
  },
}))

const project: ProjectView = {
  course_id: 'project-ladder',
  title: 'Word Frequency Counter',
  language: 'python',
  source_type: 'transcript',
  source_url: '',
  source_summary: '',
  project_goal: 'Build a word frequency counter',
  course_intro: '',
  tech_stack: ['collections'],
  entry_file: 'main.py',
  milestones: [
    {
      id: 'm1', order: 1, title: 'Set up the project', status: 'completed',
      source_grounded_description: '', source_quote: '', why: '', xp_reward: 10,
      hook: '', teach: '', example: '', celebrate: '',
      microstep: { observation: '', action: '', hint: '' },
      built_unaided: true,
    },
    {
      id: 'm2', order: 2, title: 'Import collections', status: 'current',
      source_grounded_description: 'First, import the collections module.',
      source_quote: 'First, import the collections module.', why: 'You need it to count.',
      xp_reward: 20, hook: 'Bring in the counting toolkit.',
      teach: 'collections gives you Counter, a ready-made tallier.',
      example: 'from collections import Counter', celebrate: '',
      microstep: { observation: 'Next step from the source:', action: 'Add `import collections`.', hint: 'Add import collections.' },
      review_due: true,
    },
  ],
  workspace_files: [{ path: 'main.py', content: '# main\n' }],
  current_milestone_index: 1,
  completed_milestone_ids: ['m1'],
  xp: 10,
  completed: false,
  completion_percent: 50,
  files_changed: 1,
}

type CardSpec = { id: string; stage: string; lead: string; action: string; cleared?: boolean }

function rungSession(cards: CardSpec[], overrides: Record<string, unknown> = {}) {
  return {
    lesson_id: project.course_id,
    skill: 'Import collections',
    concept: 'project-ladder:m2',
    objective: project.project_goal,
    story: { why_this: 'You need it to count.', why_next: 'Next: Define count_words' },
    milestone_id: 'm2',
    milestone_title: 'Import collections',
    milestone_order: 2,
    milestone_total: 2,
    planned_steps: cards.length + 1,
    bonus_steps: 0,
    ladder_steps: cards.length + 1,
    steps: cards.map((c) => ({
      id: c.id,
      stage: c.stage,
      widget: 'present',
      concept: 'project-ladder:m2',
      stakes: 'free',
      bonus: false,
      reason: `ladder: ${c.stage} rung for m2`,
      title: c.lead,
      question: '',
      options: [],
      content: { lead: c.lead, say: `${c.id} explains why this step exists.`, takeaway: 'Add import collections.' },
      action: c.action,
      hints: [],
      checks: [],
      cleared: Boolean(c.cleared),
    })),
    build: {
      id: 'm2-independent',
      stage: 'independent',
      widget: 'project_build',
      concept: 'project-ladder:m2',
      stakes: 'charged',
      bonus: false,
      reason: 'production: your code, verified by running it',
      title: 'Import collections',
      question: 'Add `import collections`.',
      options: [],
      content: {},
      action: '',
      hints: ['Add import collections.'],
      checks: ['Your code imports `collections`.'],
      cleared: false,
    },
    trace: [],
    demonstrated: false,
    evidence: [],
    completion_percent: 50,
    completed: false,
    summary: null,
    ...overrides,
  }
}

/** The ladder hook reads raw `fetch`; the workspace's own calls go through projectApi. */
function stubLadderFetch(session: unknown) {
  const seen: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/seen')) {
      seen.push(url.split('/session/')[1].replace('/seen', ''))
      return { ok: true, status: 200, json: async () => ({ step_id: 'x', cleared: seen, xp_awarded: 0 }) }
    }
    if (url.includes('/session')) {
      const body = typeof session === 'function' ? (session as any)(seen) : session
      return { ok: true, status: 200, json: async () => body }
    }
    return { ok: false, status: 404, json: async () => ({}) }
  }))
  return seen
}

const INTRO = { id: 'm2-introduce', stage: 'introduce', lead: 'A model of counting you did not write', action: 'Show me how' }
const SHOW = { id: 'm2-show', stage: 'show', lead: 'collections gives you Counter.', action: 'Let’s build it' }

beforeEach(() => {
  vi.clearAllMocks()
  ;(projectApi.get as any).mockResolvedValue(project)
  ;(projectApi.saveWorkspace as any).mockResolvedValue(project)
  ;(projectApi.next as any).mockResolvedValue({
    status: 'incomplete', advanced: [], current_milestone: null, checks: [], feedback: 'not yet',
    stdout: '', stderr: '', xp: 10, completion_percent: 50, completed: false, project, summary: null,
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ProjectWorkspace teaching ladder', () => {
  it('teaches the step before it offers NEXT', async () => {
    stubLadderFetch(rungSession([INTRO, SHOW]))
    render(<ProjectWorkspace courseId="project-ladder" onExit={() => {}} />)

    // The rung is on screen, in words, and the task is not.
    expect(await screen.findByText('A model of counting you did not write')).toBeInTheDocument()
    expect(screen.getByText('The idea')).toBeInTheDocument()
    // The bar counts the production rung too, even though it is answered in the
    // workspace and never rendered as a card — otherwise it starts one short.
    expect(screen.getByText('1 / 3')).toBeInTheDocument()
    const next = screen.getByRole('button', { name: /Read the step first/ })
    expect(next).toBeDisabled()
    // The old collapsed drawers are gone while a rung is outstanding: a toggle the
    // learner may skip is not a teaching sequence.
    expect(screen.queryByRole('button', { name: 'Learn more' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Show example/ })).not.toBeInTheDocument()
  })

  it('unlocks NEXT only after every rung is acknowledged, and tells the server each time', async () => {
    const seen = stubLadderFetch((acked: string[]) => rungSession(
      [INTRO, SHOW].map((c) => ({ ...c, cleared: acked.includes(c.id) })) as CardSpec[],
    ))
    render(<ProjectWorkspace courseId="project-ladder" onExit={() => {}} />)

    await screen.findByText(INTRO.lead)
    fireEvent.click(screen.getByRole('button', { name: INTRO.action }))
    await waitFor(() => expect(seen).toContain('m2-introduce'))

    await screen.findByText(SHOW.lead)
    fireEvent.click(screen.getByRole('button', { name: SHOW.action }))
    await waitFor(() => expect(seen).toContain('m2-show'))

    // Rungs done: the build card returns, and it now states what must be true.
    const next = await screen.findByRole('button', { name: /NEXT/ })
    expect(next).toBeEnabled()
    expect(screen.getByText('Your code imports `collections`.')).toBeInTheDocument()
  })

  it('falls back to the plain task card when the server has no ladder', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) })))
    render(<ProjectWorkspace courseId="project-ladder" onExit={() => {}} />)
    await waitFor(() => expect(screen.getByRole('button', { name: /NEXT/ })).toBeEnabled())
    expect(screen.getByText('Bring in the counting toolkit.')).toBeInTheDocument()
  })

  it('reports a milestone as helped when a suggestion is applied to the code', async () => {
    stubLadderFetch(rungSession([]))
    ;(projectApi.guidance as any).mockResolvedValue({
      milestone_id: 'm2', observation: '', action: '', hint: '', why: '', source_quote: '',
      suggestion: 'from collections import Counter', suggestion_note: 'Try this.', provider_used: 'openrouter',
    })
    render(<ProjectWorkspace courseId="project-ladder" onExit={() => {}} />)

    const next = await screen.findByRole('button', { name: /NEXT/ })
    expect((next as HTMLButtonElement).disabled).toBe(false)
    // Unaided so far.
    fireEvent.click(next)
    await waitFor(() => expect(projectApi.next).toHaveBeenLastCalledWith('project-ladder', expect.anything(), false))

    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    await screen.findByText('Try this.')
    fireEvent.click(screen.getByRole('button', { name: /Apply suggestion/ }))

    fireEvent.click(screen.getByRole('button', { name: /NEXT/ }))
    // Being carried through a step completes it and does not claim the learner wrote it.
    await waitFor(() => expect(projectApi.next).toHaveBeenLastCalledWith('project-ladder', expect.anything(), true))
  })

  it('marks a finished step that is overdue for review', async () => {
    stubLadderFetch(rungSession([]))
    render(<ProjectWorkspace courseId="project-ladder" onExit={() => {}} />)
    expect(await screen.findByTitle(/older than its recall gap/i)).toBeInTheDocument()
  })

  it('says which steps the learner wrote themselves when the project ends', async () => {
    stubLadderFetch(rungSession([]))
    ;(projectApi.next as any).mockResolvedValue({
      status: 'project_complete', advanced: [], current_milestone: null, checks: [],
      feedback: 'Project complete', stdout: '', stderr: '', xp: 30, completion_percent: 100,
      completed: true, project: { ...project, completed: true },
      summary: {
        title: project.title, milestones_built: ['Set up the project', 'Import collections'],
        built_unaided: ['Import collections'], completed_with_help: ['Set up the project'],
        xp: 30, files_changed: 1, tech_stack: ['collections'], steps_overdue_for_review: 1,
      },
    })
    render(<ProjectWorkspace courseId="project-ladder" onExit={() => {}} />)

    fireEvent.click(await screen.findByRole('button', { name: /NEXT/ }))
    await screen.findByText('🎉 You shipped it!')
    expect(screen.getByText('1 of 2 steps you wrote yourself')).toBeInTheDocument()
    expect(screen.getByText(/With help: Set up the project/)).toBeInTheDocument()
    // Not a participation ribbon: the summary names the one thing a percentage hides.
    expect(screen.getByText(/older than their recall/)).toBeInTheDocument()
  })
})
