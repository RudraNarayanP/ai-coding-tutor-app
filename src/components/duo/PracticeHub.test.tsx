import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { PracticeHub } from './PracticeHub'
import type { PathLesson } from './LearnPath'

const lessons: PathLesson[] = [
  {
    id: 'lesson-1',
    title: 'Hello, World!',
    order: 1,
    difficulty: 'beginner',
    duration_minutes: 5,
    status: 'completed',
    type: 'learn',
  },
  {
    id: 'lesson-2',
    title: 'Variables',
    order: 2,
    difficulty: 'beginner',
    duration_minutes: 8,
    status: 'current',
    type: 'learn',
  },
  {
    id: 'practice-1',
    title: 'Variables Practice',
    order: 3,
    difficulty: 'beginner',
    duration_minutes: 8,
    status: 'current',
    type: 'practice',
  },
]

describe('PracticeHub', () => {
  it('renders the practice workspace chrome', () => {
    render(
      <PracticeHub
        lessons={lessons}
        isLoadingLesson={false}
        onOpenLesson={() => {}}
        onOpenGuidebook={() => {}}
      />
    )

    expect(screen.getByLabelText('Practice workspace')).toBeInTheDocument()
    expect(screen.getByText('YOUR TASK')).toBeInTheDocument()
    expect(screen.getByText("Today's Review")).toBeInTheDocument()
    expect(screen.getByText('Output')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'START' })).toBeEnabled()
  })

  it('starts the current lesson from Unit Rewind', async () => {
    const user = userEvent.setup()
    const onOpenLesson = vi.fn()

    render(
      <PracticeHub
        lessons={lessons}
        isLoadingLesson={false}
        onOpenLesson={onOpenLesson}
        onOpenGuidebook={() => {}}
      />
    )

    await user.click(screen.getByRole('button', { name: 'START' }))
    expect(onOpenLesson).toHaveBeenCalledWith(lessons[1])
  })

  it('opens an unlocked practice lesson', async () => {
    const user = userEvent.setup()
    const onOpenLesson = vi.fn()

    render(
      <PracticeHub
        lessons={lessons}
        isLoadingLesson={false}
        onOpenLesson={onOpenLesson}
        onOpenGuidebook={() => {}}
      />
    )

    await user.click(screen.getByRole('button', { name: /Practice lessons/ }))
    await user.click(screen.getByRole('button', { name: 'START' }))
    expect(onOpenLesson).toHaveBeenCalledWith(lessons[2])
  })

  it('reviews a completed lesson', async () => {
    const user = userEvent.setup()
    const onOpenLesson = vi.fn()

    render(
      <PracticeHub
        lessons={lessons}
        isLoadingLesson={false}
        onOpenLesson={onOpenLesson}
        onOpenGuidebook={() => {}}
      />
    )

    await user.click(screen.getByRole('button', { name: /Completed lessons/ }))
    await user.click(screen.getByRole('button', { name: 'REVIEW' }))
    expect(onOpenLesson).toHaveBeenCalledWith(lessons[0])
  })

  it('opens the guidebook', async () => {
    const user = userEvent.setup()
    const onOpenGuidebook = vi.fn()

    render(
      <PracticeHub
        lessons={lessons}
        isLoadingLesson={false}
        onOpenLesson={() => {}}
        onOpenGuidebook={onOpenGuidebook}
      />
    )

    await user.click(screen.getByRole('button', { name: /Guidebook/ }))
    await user.click(screen.getByRole('button', { name: 'OPEN' }))
    expect(onOpenGuidebook).toHaveBeenCalledTimes(1)
  })

  it('keeps review disabled when nothing is available', () => {
    render(
      <PracticeHub
        lessons={[]}
        isLoadingLesson={false}
        onOpenLesson={() => {}}
        onOpenGuidebook={() => {}}
      />
    )

    expect(screen.getByRole('button', { name: 'START — no lesson to review' })).toBeDisabled()
  })
})
