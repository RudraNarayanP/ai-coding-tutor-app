import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ProjectWorkspace } from './ProjectWorkspace'
import { projectApi, type ProjectView, type NextResult } from '../../utils/projectApi'

vi.mock('../../utils/projectApi', () => ({
  projectApi: {
    get: vi.fn(),
    saveWorkspace: vi.fn(),
    run: vi.fn(),
    next: vi.fn(),
    guidance: vi.fn(),
  },
}))

const baseProject: ProjectView = {
  course_id: 'project-abc',
  title: 'Word Frequency Counter',
  language: 'python',
  source_type: 'transcript',
  source_url: '',
  source_summary: '',
  project_goal: 'Build a word frequency counter',
  tech_stack: ['collections'],
  entry_file: 'main.py',
  milestones: [
    {
      id: 'm1', order: 1, title: 'Set up the project', status: 'completed',
      source_grounded_description: '', source_quote: '', why: '', xp_reward: 10,
      hook: '', teach: '', example: '', celebrate: 'Nailed it! 🎯',
      microstep: { observation: '', action: '', hint: '' },
    },
    {
      id: 'm2', order: 2, title: 'Import collections', status: 'current',
      source_grounded_description: 'First, import the collections module.',
      source_quote: 'First, import the collections module.', why: 'You need it to count.', xp_reward: 20,
      hook: 'Bring in the counting toolkit.',
      teach: 'The collections module gives you Counter, a ready-made word tallier. It saves you from hand-rolling a dict.',
      example: 'from collections import Counter',
      celebrate: 'Toolkit imported! 🧰',
      microstep: { observation: 'Next step from the source:', action: 'Import the collections module.', hint: 'Add import collections.' },
    },
    {
      id: 'm3', order: 3, title: 'Define count_words', status: 'pending',
      source_grounded_description: '', source_quote: '', why: '', xp_reward: 20,
      hook: '', teach: '', example: '', celebrate: '',
      microstep: { observation: '', action: '', hint: '' },
    },
  ],
  workspace_files: [{ path: 'main.py', content: '# Word Frequency Counter\n' }],
  current_milestone_index: 1,
  completed_milestone_ids: ['m1'],
  xp: 10,
  completed: false,
  completion_percent: 33,
  files_changed: 1,
}

describe('ProjectWorkspace', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ;(projectApi.get as any).mockResolvedValue(baseProject)
    ;(projectApi.saveWorkspace as any).mockResolvedValue(baseProject)
  })

  it('renders the persistent workspace with milestones, editor and NEXT', async () => {
    render(<ProjectWorkspace courseId="project-abc" onExit={() => {}} />)

    await waitFor(() => screen.getByText('Word Frequency Counter'))
    // Milestone map with source-grounded steps ("Import collections" also appears
    // as the current-step heading, hence getAllByText).
    expect(screen.getAllByText('Import collections').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Define count_words')).toBeInTheDocument()
    // Microstep guidance for the current milestone
    expect(screen.getByText(/Import the collections module\./)).toBeInTheDocument()
    // Rich, engaging content: hook headline + teach explanation + Show example
    expect(screen.getByText('Bring in the counting toolkit.')).toBeInTheDocument()
    expect(screen.getByText(/ready-made word tallier/)).toBeInTheDocument()
    expect(screen.getByText('Show example')).toBeInTheDocument()
    // Progress + editor + NEXT
    expect(screen.getByText('33% complete')).toBeInTheDocument()
    expect(screen.getByLabelText('Editor for main.py')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /NEXT/ })).toBeInTheDocument()
  })

  it('runs the workspace and shows terminal output', async () => {
    ;(projectApi.run as any).mockResolvedValue({ ran_ok: true, stdout: 'Counter({"a": 3})\n', stderr: '', error: null })
    render(<ProjectWorkspace courseId="project-abc" onExit={() => {}} />)
    await waitFor(() => screen.getByText('Word Frequency Counter'))

    fireEvent.click(screen.getByRole('button', { name: /Run/ }))
    await waitFor(() => expect(screen.getAllByText(/Counter/).length).toBeGreaterThanOrEqual(1))
    expect(projectApi.run).toHaveBeenCalled()
  })

  it('verifies via NEXT and shows failing checks with guidance', async () => {
    const nextResult: NextResult = {
      status: 'incomplete',
      advanced: [{ milestone_id: 'm1', title: 'Set up the project', xp_awarded: 0, already_completed: true }],
      current_milestone: baseProject.milestones[1],
      checks: [{ description: 'Your code imports `collections`.', passed: false, detail: 'No import of `collections` found yet.' }],
      feedback: 'No import of `collections` found yet.',
      stdout: '', stderr: '', xp: 10, completion_percent: 33, completed: false,
      project: baseProject,
    }
    ;(projectApi.next as any).mockResolvedValue(nextResult)
    render(<ProjectWorkspace courseId="project-abc" onExit={() => {}} />)
    await waitFor(() => screen.getByText('Word Frequency Counter'))

    fireEvent.click(screen.getByRole('button', { name: /NEXT/ }))
    await waitFor(() => expect(screen.getAllByText(/No import of/).length).toBeGreaterThanOrEqual(1))
    // Failing check is surfaced to the learner
    expect(screen.getByText(/Your code imports/)).toBeInTheDocument()
  })

  it('offers a read-only AI suggestion that the learner explicitly applies', async () => {
    ;(projectApi.guidance as any).mockResolvedValue({
      milestone_id: 'm2', observation: '', action: '', hint: '', why: '', source_quote: '',
      suggestion: 'import collections', suggestion_note: 'Add the import at the top.', provider_used: 'openrouter',
    })
    render(<ProjectWorkspace courseId="project-abc" onExit={() => {}} />)
    await waitFor(() => screen.getByText('Word Frequency Counter'))

    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    await waitFor(() => screen.getByText('Apply suggestion'))
    // The suggestion is shown but NOT auto-applied; editor still holds original content.
    const editor = screen.getByLabelText('Editor for main.py') as HTMLTextAreaElement
    expect(editor.value).not.toContain('import collections')

    fireEvent.click(screen.getByText('Apply suggestion'))
    expect((screen.getByLabelText('Editor for main.py') as HTMLTextAreaElement).value).toContain('import collections')
  })
})
