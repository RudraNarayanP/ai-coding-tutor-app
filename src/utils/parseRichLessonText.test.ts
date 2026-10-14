import { describe, expect, it } from 'vitest'
import { parseRichLessonText } from './parseRichLessonText'

describe('parseRichLessonText', () => {
  it('parses inline code and inline math', () => {
    const segments = parseRichLessonText('Set `area` to $\\frac{a}{b}$ here.')
    expect(segments).toEqual([
      { type: 'text', value: 'Set ' },
      { type: 'code', value: 'area' },
      { type: 'text', value: ' to ' },
      { type: 'math', value: '\\frac{a}{b}', display: false },
      { type: 'text', value: ' here.' },
    ])
  })

  it('parses display math with $$ delimiters', () => {
    const segments = parseRichLessonText('Before $$x^2$$ after')
    expect(segments).toEqual([
      { type: 'text', value: 'Before ' },
      { type: 'math', value: 'x^2', display: true },
      { type: 'text', value: ' after' },
    ])
  })

  it('parses the foundations checkpoint formula as display math', () => {
    const segments = parseRichLessonText(
      'For a triangle with base $10$ and height $5$, set `area` to the triangle formula. $$\\dfrac{\\text{base} \\times \\text{height}}{2}$$ The test checks `area == 25`.',
    )
    expect(segments).toEqual([
      { type: 'text', value: 'For a triangle with base ' },
      { type: 'math', value: '10', display: false },
      { type: 'text', value: ' and height ' },
      { type: 'math', value: '5', display: false },
      { type: 'text', value: ', set ' },
      { type: 'code', value: 'area' },
      { type: 'text', value: ' to the triangle formula. ' },
      { type: 'math', value: '\\dfrac{\\text{base} \\times \\text{height}}{2}', display: true },
      { type: 'text', value: ' The test checks ' },
      { type: 'code', value: 'area == 25' },
      { type: 'text', value: '.' },
    ])
  })

  it('parses \\(...\\) and \\[...\\] delimiters', () => {
    expect(parseRichLessonText('\\(a+b\\)')).toEqual([
      { type: 'math', value: 'a+b', display: false },
    ])
    expect(parseRichLessonText('\\[E=mc^2\\]')).toEqual([
      { type: 'math', value: 'E=mc^2', display: true },
    ])
  })
})
