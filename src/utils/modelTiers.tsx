import React from 'react'

// Shared OpenRouter model-tier helpers for the Home and Settings pickers.
// The tier data itself lives in ONE place: backend/api_settings.py
// (OPENROUTER_MODEL_TIERS), served by GET /api/settings.

export type ModelQuality = 'recommended' | 'mediocre' | 'not_ideal' | 'untested'

export interface ModelPreset {
  id: string
  label: string
  /** Billing tier: "free" or "paid". */
  tier: string
  quality?: ModelQuality | string
  reason?: string
  recommended?: boolean
}

export interface QualityGroup {
  id: string
  label: string
}

export const DEFAULT_QUALITY_GROUPS: QualityGroup[] = [
  { id: 'recommended', label: 'Recommended' },
  { id: 'mediocre', label: 'Mediocre' },
  { id: 'not_ideal', label: 'Not ideal' },
  { id: 'untested', label: 'Untested' },
]

export function groupPresetsByQuality(
  presets: ModelPreset[],
  groups: QualityGroup[] = DEFAULT_QUALITY_GROUPS,
): Array<{ group: QualityGroup; presets: ModelPreset[] }> {
  const known = new Set(groups.map((g) => g.id))
  const out = groups
    .map((group) => ({ group, presets: presets.filter((p) => (p.quality || 'untested') === group.id) }))
    .filter((g) => g.presets.length > 0)
  const unknown = presets.filter((p) => !known.has(p.quality || 'untested'))
  if (unknown.length) out.push({ group: { id: 'other', label: 'Other' }, presets: unknown })
  return out
}

export function findPreset(presets: ModelPreset[], id: string): ModelPreset | undefined {
  return presets.find((p) => p.id === id)
}

export function qualityLabel(quality: string | undefined, groups: QualityGroup[] = DEFAULT_QUALITY_GROUPS): string {
  return groups.find((g) => g.id === quality)?.label || 'Untested'
}

/** Top Recommended model from the served list (backend default), else the first preset. */
export function defaultModelId(presets: ModelPreset[], served?: string): string {
  if (served) return served
  return (presets.find((p) => p.quality === 'recommended') || presets[0])?.id || ''
}

/** <optgroup> blocks for a <select>; each option carries its one-line reason as a tooltip. */
export function ModelPresetOptions({
  presets,
  groups,
  markPaid = false,
}: {
  presets: ModelPreset[]
  groups?: QualityGroup[]
  markPaid?: boolean
}) {
  return (
    <>
      {groupPresetsByQuality(presets, groups && groups.length ? groups : DEFAULT_QUALITY_GROUPS).map(
        ({ group, presets: items }) => (
          <optgroup key={group.id} label={group.label}>
            {items.map((pr) => (
              <option key={pr.id} value={pr.id} title={pr.reason || ''}>
                {pr.label}
                {markPaid && pr.tier === 'paid' ? ' ⚠ credits' : ''}
              </option>
            ))}
          </optgroup>
        ),
      )}
    </>
  )
}

/** "Recommended — <reason>" for the selected model, or a custom-model note. */
export function ModelQualityNote({
  presets,
  modelId,
  groups,
  style,
}: {
  presets: ModelPreset[]
  modelId: string
  groups?: QualityGroup[]
  style?: React.CSSProperties
}) {
  const pr = findPreset(presets, modelId)
  const text = pr
    ? `${qualityLabel(pr.quality, groups && groups.length ? groups : DEFAULT_QUALITY_GROUPS)} — ${pr.reason || 'no evidence yet'}`
    : modelId
      ? 'Custom model — not in the tested list.'
      : ''
  if (!text) return null
  return (
    <div data-testid="model-quality-note" style={style}>
      {text}
    </div>
  )
}
