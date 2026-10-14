import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { LessonRichText } from './LessonRichText'

describe('LessonRichText', () => {
  it('renders KaTeX for inline math', () => {
    const { container } = render(<LessonRichText text="Area is $\\frac{1}{2}bh$." />)
    expect(container.querySelector('.katex')).toBeTruthy()
    expect(container.textContent).toContain('Area is')
  })

  it('renders a display fraction without falling back to raw TeX', () => {
    const { container } = render(
      <LessonRichText
        block
        text={'Set `area` to $$\\dfrac{\\text{base} \\times \\text{height}}{2}$$.'}
      />,
    )
    expect(container.querySelector('.katex-display')).toBeTruthy()
    expect(container.querySelector('.frac-line')).toBeTruthy()
    expect(container.querySelector('.lesson-rich-math--fallback')).toBeNull()
    expect(screen.getByText('area')).toHaveClass('ew-task-code')
  })

  it('renders backtick code alongside math', () => {
    render(<LessonRichText text="Check `area == 25` and $x$." />)
    expect(screen.getByText('area == 25')).toHaveClass('ew-task-code')
  })
})
