import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import {
  ModelPresetOptions,
  ModelQualityNote,
  defaultModelId,
  groupPresetsByQuality,
  type ModelPreset,
} from './modelTiers'

const presets: ModelPreset[] = [
  { id: 'a/ultra:free', label: 'Ultra (free)', tier: 'free', quality: 'recommended', reason: 'Shippable courses.' },
  { id: 'b/super:free', label: 'Super (free)', tier: 'free', quality: 'mediocre', reason: 'Weak checks.' },
  { id: 'c/tiny:free', label: 'Tiny (free)', tier: 'free', quality: 'not_ideal', reason: 'False discards.' },
  { id: 'd/paid', label: 'Paid', tier: 'paid', quality: 'untested', reason: 'Needs credits.' },
]

describe('modelTiers', () => {
  it('groups presets in Recommended → Mediocre → Not ideal → Untested order', () => {
    const groups = groupPresetsByQuality([...presets].reverse())
    expect(groups.map((g) => g.group.label)).toEqual(['Recommended', 'Mediocre', 'Not ideal', 'Untested'])
    expect(groups[0].presets.map((p) => p.id)).toEqual(['a/ultra:free'])
  })

  it('defaults to the served default, else the top Recommended model', () => {
    expect(defaultModelId(presets, 'b/super:free')).toBe('b/super:free')
    expect(defaultModelId(presets)).toBe('a/ultra:free')
    expect(defaultModelId([])).toBe('')
  })

  it('renders optgroups with reasons as tooltips and marks paid models', () => {
    render(
      <select aria-label="m" defaultValue="a/ultra:free">
        <ModelPresetOptions presets={presets} markPaid />
      </select>,
    )
    const groups = document.querySelectorAll('optgroup')
    expect(Array.from(groups).map((g) => g.getAttribute('label'))).toEqual([
      'Recommended',
      'Mediocre',
      'Not ideal',
      'Untested',
    ])
    expect(screen.getByRole('option', { name: 'Ultra (free)' }).getAttribute('title')).toBe('Shippable courses.')
    expect(screen.getByRole('option', { name: /Paid ⚠ credits/ })).toBeTruthy()
  })

  it('shows the tier and one-line reason for the selected model', () => {
    const { rerender } = render(<ModelQualityNote presets={presets} modelId="c/tiny:free" />)
    expect(screen.getByTestId('model-quality-note').textContent).toBe('Not ideal — False discards.')
    rerender(<ModelQualityNote presets={presets} modelId="x/custom" />)
    expect(screen.getByTestId('model-quality-note').textContent).toMatch(/Custom model/)
  })
})
