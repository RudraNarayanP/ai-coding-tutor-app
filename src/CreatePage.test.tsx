import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { CreatePage } from '../src/components/CreatePage'
import { CreateCourseError, projectApi } from '../src/utils/projectApi'

vi.mock('../src/utils/projectApi', async () => {
  const actual = await vi.importActual<typeof import('../src/utils/projectApi')>('../src/utils/projectApi')
  return {
    ...actual,
    projectApi: {
      ...actual.projectApi,
      list: vi.fn().mockResolvedValue([]),
      create: vi.fn(),
      get: vi.fn(),
      remove: vi.fn(),
    },
  }
})

describe('CreatePage Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(projectApi.list).mockResolvedValue([])
    vi.mocked(projectApi.create).mockReset()
  })

  it('renders the guided-project builder input step', () => {
    const handleCourseReady = vi.fn()
    render(<CreatePage onCourseReady={handleCourseReady} />)

    expect(screen.getByText('✨ AI Course Builder')).toBeInTheDocument()
    expect(screen.getByText('YouTube URL / Playlist')).toBeInTheDocument()
    expect(screen.getByText('Paste Transcript / Notes')).toBeInTheDocument()
    expect(screen.getByText('Upload File')).toBeInTheDocument()
    // Guided Project is the only build mode now (broken Interactive Course removed).
    expect(screen.getByText('Build Guided Project 🛠️')).toBeInTheDocument()
    expect(screen.queryByText(/Interactive Course/)).toBeNull()
  })

  it('allows entering project title and youtube url', () => {
    const handleCourseReady = vi.fn()
    render(<CreatePage onCourseReady={handleCourseReady} />)

    const titleInput = screen.getByPlaceholderText('e.g., Reproduce GPT-2 (124M)')
    const urlInput = screen.getByPlaceholderText('https://www.youtube.com/watch?v=... or playlist URL')

    fireEvent.change(titleInput, { target: { value: 'Reproduce GPT-2' } })
    fireEvent.change(urlInput, { target: { value: 'https://www.youtube.com/watch?v=abc12345' } })

    expect(titleInput).toHaveValue('Reproduce GPT-2')
    expect(urlInput).toHaveValue('https://www.youtube.com/watch?v=abc12345')
  })

  it('shows a rejection state and does not open a workspace', async () => {
    vi.mocked(projectApi.create).mockRejectedValue(
      new CreateCourseError(
        "This video doesn't contain enough relevant technical content to create a meaningful coding project. Try a tutorial that builds a specific application, algorithm, or technical system.",
        {
          errorCode: 'source_rejected',
          decision: 'reject',
          nextStep: 'Try a tutorial that builds a specific application, algorithm, or technical system.',
        }
      )
    )
    render(<CreatePage />)
    fireEvent.click(screen.getByText('Paste Transcript / Notes'))
    fireEvent.change(screen.getByPlaceholderText(/Paste raw transcript/), {
      target: { value: 'write him a draft then create our memo' },
    })
    fireEvent.click(screen.getByText('Build Guided Project 🛠️'))

    const gate = await screen.findByTestId('create-source-gate')
    expect(gate).toHaveClass('create-gate-reject')
    expect(gate).toHaveTextContent(/isn't suitable for a coding project/i)
    expect(screen.queryByLabelText('Guided project workspace')).toBeNull()
    expect(screen.queryByText(/0%/)).toBeNull()
  })

  it('shows a rejection state for assistant-usage sources', async () => {
    vi.mocked(projectApi.create).mockRejectedValue(
      new CreateCourseError(
        'This source is about using an AI assistant (prompting, tips, or productivity chats), not about implementing software. Create Course needs a coding or ML tutorial that builds a specific application, algorithm, or technical system.',
        {
          errorCode: 'source_rejected',
          decision: 'reject',
          nextStep: 'Try a tutorial that builds a specific application, algorithm, or technical system.',
        }
      )
    )
    render(<CreatePage />)
    fireEvent.click(screen.getByText('Paste Transcript / Notes'))
    fireEvent.change(screen.getByPlaceholderText(/Paste raw transcript/), {
      target: { value: '36 ChatGPT tips. Assign roles to ChatGPT. Write a birthday letter.' },
    })
    fireEvent.click(screen.getByText('Build Guided Project 🛠️'))

    const gate = await screen.findByTestId('create-source-gate')
    expect(gate).toHaveClass('create-gate-reject')
    expect(gate).toHaveTextContent(/isn't suitable for a coding project/i)
    expect(gate).toHaveTextContent(/AI assistant/i)
    expect(screen.queryByLabelText('Guided project workspace')).toBeNull()
  })

  it('shows an insufficient state with a next step and does not invent a course', async () => {
    vi.mocked(projectApi.create).mockRejectedValue(
      new CreateCourseError(
        "This source may be related to programming, but there isn't enough reliable material to create a meaningful coding project.",
        {
          errorCode: 'source_insufficient',
          decision: 'insufficient',
          missingInformation: ['a clear project goal', 'concrete technical material'],
          nextStep: 'Paste a fuller transcript, or pick a hands-on tutorial that shows a specific application, algorithm, or technical system being built.',
        }
      )
    )
    render(<CreatePage />)
    fireEvent.click(screen.getByText('Paste Transcript / Notes'))
    fireEvent.change(screen.getByPlaceholderText(/Paste raw transcript/), {
      target: { value: 'Python is great. Algorithms are important.' },
    })
    fireEvent.click(screen.getByText('Build Guided Project 🛠️'))

    const gate = await screen.findByTestId('create-source-gate')
    expect(gate).toHaveClass('create-gate-insufficient')
    expect(gate).toHaveTextContent(/Not enough information/i)
    expect(gate).toHaveTextContent(/Paste a fuller transcript/)
    expect(screen.queryByLabelText('Guided project workspace')).toBeNull()
  })

  it('opens the workspace for an accepted source', async () => {
    vi.mocked(projectApi.create).mockResolvedValue({
      course_id: 'project-ok',
      title: 'Word Frequency Counter',
      language: 'python',
      source_type: 'transcript',
      source_url: '',
      source_summary: '',
      project_goal: 'Build a word frequency counter',
      tech_stack: ['collections'],
      entry_file: 'main.py',
      milestones: [],
      workspace_files: [{ path: 'main.py', content: '#' }],
      current_milestone_index: 0,
      completed_milestone_ids: [],
      xp: 0,
      completed: false,
      completion_percent: 0,
      files_changed: 0,
    } as Awaited<ReturnType<typeof projectApi.create>>)
    vi.mocked(projectApi.get).mockResolvedValue({
      course_id: 'project-ok',
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
          id: 'm1',
          order: 1,
          title: 'Set up the project',
          status: 'current',
          source_grounded_description: 'Create the entry file.',
          source_quote: '',
          microstep: { observation: '', action: 'Create main.py', hint: '' },
          why: '',
          hook: '',
          teach: '',
          example: '',
          celebrate: '',
          xp_reward: 10,
        },
      ],
      workspace_files: [{ path: 'main.py', content: '#' }],
      current_milestone_index: 0,
      completed_milestone_ids: [],
      xp: 0,
      completed: false,
      completion_percent: 0,
      files_changed: 0,
    } as Awaited<ReturnType<typeof projectApi.get>>)

    render(<CreatePage />)
    fireEvent.click(screen.getByText('Paste Transcript / Notes'))
    fireEvent.change(screen.getByPlaceholderText(/Paste raw transcript/), {
      target: { value: 'In this tutorial we build a word frequency counter.' },
    })
    fireEvent.click(screen.getByText('Build Guided Project 🛠️'))

    await waitFor(() => {
      expect(projectApi.create).toHaveBeenCalled()
    })
    expect(await screen.findByLabelText('Guided project workspace')).toBeInTheDocument()
  })

  it('shows a cancel button while building and aborts the request', async () => {
    let rejectCreate: (reason?: unknown) => void = () => {}
    vi.mocked(projectApi.create).mockImplementation(
      (_payload: unknown, options?: { signal?: AbortSignal }) =>
        new Promise((_resolve, reject) => {
          rejectCreate = reject
          options?.signal?.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'))
          })
        })
    )

    render(<CreatePage />)

    fireEvent.change(screen.getByPlaceholderText('e.g., Reproduce GPT-2 (124M)'), {
      target: { value: 'My Project' },
    })
    fireEvent.click(screen.getByText('Build Guided Project 🛠️'))

    await waitFor(() => expect(screen.getByRole('status')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Cancel build' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Cancel build' }))
    rejectCreate(new DOMException('Aborted', 'AbortError'))

    await waitFor(() => expect(screen.getByText('Build cancelled.')).toBeInTheDocument())
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('deletes a saved project from the resume list', async () => {
    vi.mocked(projectApi.list).mockResolvedValue([
      {
        course_id: 'project-bad',
        title: 'Intro to Large Language Models',
        language: 'python',
        completion_percent: 50,
        completed: false,
        milestone_count: 8,
        updated_at: 1,
      },
    ])
    vi.mocked(projectApi.remove).mockResolvedValue({ status: 'deleted' })
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<CreatePage />)
    await waitFor(() => screen.getByText('Intro to Large Language Models'))
    fireEvent.click(screen.getByRole('button', { name: 'Delete Intro to Large Language Models' }))
    await waitFor(() => expect(projectApi.remove).toHaveBeenCalledWith('project-bad'))
    await waitFor(() => expect(screen.queryByText('Intro to Large Language Models')).toBeNull())
  })
})
