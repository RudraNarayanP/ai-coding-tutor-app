import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { CreatePage } from '../src/components/CreatePage'

describe('CreatePage Component', () => {
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
})
