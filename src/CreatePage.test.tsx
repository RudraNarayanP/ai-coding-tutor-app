import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { CreatePage } from '../src/components/CreatePage'

describe('CreatePage Component', () => {
  it('renders input step with material type tabs and generate button', () => {
    const handleCourseReady = vi.fn()
    render(<CreatePage onCourseReady={handleCourseReady} />)

    expect(screen.getByText('✨ AI Course Builder')).toBeInTheDocument()
    expect(screen.getByText('YouTube URL / Playlist')).toBeInTheDocument()
    expect(screen.getByText('Paste Transcript / Notes')).toBeInTheDocument()
    expect(screen.getByText('Upload File')).toBeInTheDocument()
    // Create Course is now dual-mode: Guided Project (default) and Interactive Course.
    expect(screen.getByText('🛠️ Guided Project')).toBeInTheDocument()
    expect(screen.getByText('📚 Interactive Course')).toBeInTheDocument()
    expect(screen.getByText('Build Guided Project 🛠️')).toBeInTheDocument()
  })

  it('can switch to interactive course mode', () => {
    const handleCourseReady = vi.fn()
    render(<CreatePage onCourseReady={handleCourseReady} />)

    fireEvent.click(screen.getByText('📚 Interactive Course'))
    expect(screen.getByText('Generate Interactive Course ✨')).toBeInTheDocument()
  })

  it('allows entering course title and youtube url', () => {
    const handleCourseReady = vi.fn()
    render(<CreatePage onCourseReady={handleCourseReady} />)

    const titleInput = screen.getByPlaceholderText('e.g., Master Quantum Mechanics & Computing')
    const urlInput = screen.getByPlaceholderText('https://www.youtube.com/watch?v=... or playlist URL')

    fireEvent.change(titleInput, { target: { value: 'React Essentials' } })
    fireEvent.change(urlInput, { target: { value: 'https://www.youtube.com/watch?v=abc12345' } })

    expect(titleInput).toHaveValue('React Essentials')
    expect(urlInput).toHaveValue('https://www.youtube.com/watch?v=abc12345')
  })
})
