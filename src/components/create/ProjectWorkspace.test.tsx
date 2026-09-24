import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ProjectWorkspace } from './ProjectWorkspace'
import { projectApi, type ProjectView, type NextResult } from '../../utils/projectApi'

vi.mock('../../utils/projectApi', () => ({
  projectApi: {
    get: vi.fn(),
    saveWorkspace: vi.fn(),
    run: vi.fn(),
    exec: vi.fn(),
    next: vi.fn(),
    guidance: vi.fn(),
    remove: vi.fn(),
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
  course_intro: 'Build a word frequency counter step by step, using collections as in the source tutorial.',
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
      microstep: { observation: 'This step brings in collections from the tutorial.', action: 'Add `import collections` to your code.', hint: 'Add import collections.' },
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
    expect(screen.getByText(/Add `import collections`/)).toBeInTheDocument()
    // Concise default view: observation + action; teach is behind Learn more
    expect(screen.getByText('Bring in the counting toolkit.')).toBeInTheDocument()
    expect(screen.getByText(/brings in collections/)).toBeInTheDocument()
    expect(screen.getByText('Learn more')).toBeInTheDocument()
    expect(screen.queryByText(/ready-made word tallier/)).toBeNull()
    fireEvent.click(screen.getByText('Learn more'))
    expect(screen.getByText(/ready-made word tallier/)).toBeInTheDocument()
    // Progress + editor + NEXT
    expect(screen.getByText('33% complete')).toBeInTheDocument()
    expect(screen.getByLabelText('Editor for main.py')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /NEXT/ })).toBeInTheDocument()
    expect(screen.getByText('Terminal')).toBeInTheDocument()
    expect(screen.getByLabelText('Terminal command')).toBeInTheDocument()
  })

  it('runs the workspace and shows terminal output', async () => {
    ;(projectApi.exec as any).mockResolvedValue({
      command: 'python main.py',
      ran_ok: true,
      stdout: 'Counter({"a": 3})\n',
      stderr: '',
      error: null,
      exit_code: 0,
      cwd: '/workspace',
    })
    render(<ProjectWorkspace courseId="project-abc" onExit={() => {}} />)
    await waitFor(() => screen.getByText('Word Frequency Counter'))

    expect(screen.getByLabelText('Terminal')).toBeInTheDocument()
    expect(screen.getByLabelText('Terminal command')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Run project/ }))
    await waitFor(() => expect(screen.getAllByText(/Counter/).length).toBeGreaterThanOrEqual(1))
    expect(projectApi.exec).toHaveBeenCalled()
  })

  it('sends typed pip install commands to the isolated sandbox', async () => {
    ;(projectApi.exec as any).mockResolvedValue({
      command: 'pip install requests',
      ran_ok: true,
      stdout: 'Successfully installed requests\n',
      stderr: '',
      error: null,
      exit_code: 0,
      cwd: '/workspace',
    })
    render(<ProjectWorkspace courseId="project-abc" onExit={() => {}} />)
    await waitFor(() => screen.getByText('Word Frequency Counter'))

    const input = screen.getByLabelText('Terminal command') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'pip install requests' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => expect(screen.getByText(/Successfully installed requests/)).toBeInTheDocument())
    expect(projectApi.exec).toHaveBeenCalledWith('project-abc', expect.any(Array), 'pip install requests')
  })

  it('recalls submitted commands from history with the arrow keys', async () => {
    ;(projectApi.exec as any).mockResolvedValue({
      command: 'ls',
      ran_ok: true,
      stdout: 'main.py',
      stderr: '',
      error: null,
      exit_code: 0,
      cwd: '/workspace',
    })
    render(<ProjectWorkspace courseId="project-abc" onExit={() => {}} />)
    await waitFor(() => screen.getByText('Word Frequency Counter'))

    const input = screen.getByLabelText('Terminal command') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'ls' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => expect(projectApi.exec).toHaveBeenCalled())
    expect(input.value).toBe('')

    fireEvent.keyDown(input, { key: 'ArrowUp' })
    expect(input.value).toBe('ls')
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    expect(input.value).toBe('')
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

  it('clears stale verification feedback when the learner edits code (no false negative)', async () => {
    const nextResult: NextResult = {
      status: 'incomplete',
      advanced: [],
      current_milestone: baseProject.milestones[1],
      checks: [{ description: 'Your code imports `collections`.', passed: false, detail: 'No import of `collections` found yet.' }],
      feedback: 'No import of `collections` found yet.',
      stdout: '', stderr: '', xp: 10, completion_percent: 33, completed: false,
      project: baseProject,
    }
    ;(projectApi.next as any).mockResolvedValue(nextResult)
    render(<ProjectWorkspace courseId="project-abc" onExit={() => {}} />)
    await waitFor(() => screen.getByText('Word Frequency Counter'))

    // Fail verification -> stale ✗ feedback is shown.
    fireEvent.click(screen.getByRole('button', { name: /NEXT/ }))
    await waitFor(() => expect(screen.getAllByText(/No import of/).length).toBeGreaterThanOrEqual(1))

    // Now the learner edits the code (adds the import). The stale ✗ must disappear
    // immediately instead of falsely claiming the requirement is still missing.
    const editor = screen.getByLabelText('Editor for main.py') as HTMLTextAreaElement
    fireEvent.change(editor, { target: { value: 'import collections\n' } })
    await waitFor(() => expect(screen.queryByText(/No import of/)).toBeNull())
  })

  it('does not dump raw transcript speech as the default lesson action', async () => {
    const leaky = {
      ...baseProject,
      milestones: baseProject.milestones.map((m) =>
        m.id === 'm2'
          ? {
              ...m,
              hook: 'Your LLM is a confident liar.',
              microstep: {
                observation: 'Your LLM is a confident liar.',
                action:
                  "about this fish it's not going to exactly parrot the documents that it saw in the training set but again it's some kind of a lossy compression",
                hint: 'Call hallucination.',
              },
            }
          : m
      ),
    }
    ;(projectApi.get as any).mockResolvedValue(leaky)
    render(<ProjectWorkspace courseId="project-abc" onExit={() => {}} />)
    await waitFor(() => screen.getByText('Word Frequency Counter'))
    expect(screen.queryByText(/about this fish/i)).toBeNull()
    expect(screen.queryByText(/lossy compression/i)).toBeNull()
    expect(screen.getByText(/Complete this step: Import collections/)).toBeInTheDocument()
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

  it('shows a concise Why explanation, not a raw transcript dump (bugs A/B/C)', async () => {
    const dump =
      "hello everybody welcome back going from tensor flow to pytorch Friendly and so it's much easier " +
      'to load and work with huggingface transformers so import Transformers and then we can load the model'
    const project: ProjectView = {
      ...baseProject,
      title: 'Reproduce GPT-2',
      project_goal: 'Reproduce GPT-2 from the tutorial',
      tech_stack: ['torch', 'transformers'],
      milestones: [
        baseProject.milestones[0],
        {
          id: 'm2',
          order: 2,
          title: 'Import Transformers',
          status: 'current',
          source_grounded_description:
            'Load the Transformers library so you can use it in this project. Add the required import to `main.py`.',
          source_quote: dump,
          why: 'Later steps need the transformers package available. Importing it first matches the tutorial.',
          xp_reward: 20,
          hook: 'Bring in the model library.',
          teach: 'The transformers package loads pretrained GPT-2 weights. Import it before you call from_pretrained.',
          example: 'from transformers import GPT2LMHeadModel',
          celebrate: '',
          microstep: {
            observation: 'Next step from the tutorial:',
            action: 'Add `import transformers` at the top of `main.py` (or `from transformers import ...`).',
            hint: 'Use `import transformers` or `from transformers import ...` — package names are lowercase.',
          },
        },
        baseProject.milestones[2],
      ],
    }
    ;(projectApi.get as any).mockResolvedValue(project)
    render(<ProjectWorkspace courseId="project-gpt2" onExit={() => {}} />)
    await waitFor(() => screen.getByText('Reproduce GPT-2'))

    // A: description is concise, not the caption.
    expect(screen.getByText(/Load the Transformers library/)).toBeInTheDocument()
    expect(screen.queryByText(/tensor flow to pytorch/i)).toBeNull()
    // C: instructions use the real package name, not "Add an 'import Transformers'".
    expect(screen.getByText(/Add `import transformers`/)).toBeInTheDocument()
    expect(screen.queryByText(/Add an/)).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Why?' }))
    // B: Why is a useful explanation, not "From the source:" + the caption.
    const whyBody = document.querySelector('.pw-why-body')
    expect(whyBody?.textContent).toMatch(/Later steps need the transformers package/)
    expect(whyBody?.textContent || '').not.toMatch(/tensor flow to pytorch/i)
    expect(whyBody?.querySelector('.pw-source-note')).toBeNull()
  })

  it('does not render a persisted caption dump in the description or Why (defense)', async () => {
    const dump =
      "hello everybody welcome back going from tensor flow to pytorch Friendly and so it's much easier " +
      'to load and work with huggingface transformers so import Transformers and then we can load the model ' +
      'with from_pretrained and so we start by writing the neural net so define a class called GPT'
    const project: ProjectView = {
      ...baseProject,
      title: 'Reproduce GPT-2',
      milestones: [
        baseProject.milestones[0],
        {
          ...baseProject.milestones[1],
          title: 'Import Transformers',
          source_grounded_description: dump,
          source_quote: dump,
          why: dump,
          teach: dump,
          microstep: {
            observation: dump.slice(0, 200),
            action: dump,
            hint: "Add an 'import Transformers' (or 'from Transformers import ...') statement.",
          },
        },
        baseProject.milestones[2],
      ],
    }
    ;(projectApi.get as any).mockResolvedValue(project)
    render(<ProjectWorkspace courseId="project-gpt2" onExit={() => {}} />)
    await waitFor(() => screen.getAllByText('Import Transformers').length)
    expect(screen.queryByText(/tensor flow to pytorch/i)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Why?' }))
    expect(screen.queryByText(/tensor flow to pytorch/i)).toBeNull()
    expect(screen.getByText(/part of building the project from the tutorial/)).toBeInTheDocument()
  })

  it('keeps other Create Course tutorials readable (bug D) and Run/NEXT working (bug E)', async () => {
    render(<ProjectWorkspace courseId="project-abc" onExit={() => {}} />)
    await waitFor(() => screen.getByText('Word Frequency Counter'))
    expect(screen.getByText(/import the collections module/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Why?' }))
    expect(screen.getByText('You need it to count.')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /Run/ })[0]).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /NEXT/ })).toBeInTheDocument()
  })

  it('deletes the open project from the workspace header', async () => {
    ;(projectApi.remove as any).mockResolvedValue({ status: 'deleted' })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const onExit = vi.fn()
    render(<ProjectWorkspace courseId="project-abc" onExit={onExit} />)
    await waitFor(() => screen.getByText('Word Frequency Counter'))
    fireEvent.click(screen.getByRole('button', { name: 'Delete this project' }))
    await waitFor(() => expect(projectApi.remove).toHaveBeenCalledWith('project-abc'))
    expect(onExit).toHaveBeenCalled()
  })
})
