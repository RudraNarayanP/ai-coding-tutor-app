import { describe, expect, it } from 'vitest'
import { DEFAULT_APP_LOCATION, hashToLocation, locationToHash } from './appHistory'

describe('appHistory', () => {
  it('round-trips tab-only routes', () => {
    expect(locationToHash({ tab: 'practice', lessonId: null })).toBe('#/practice')
    expect(hashToLocation('#/practice')).toEqual({ tab: 'practice', lessonId: null })
  })

  it('round-trips learn lesson routes', () => {
    const loc = { tab: 'learn' as const, lessonId: 'lesson-2' }
    expect(locationToHash(loc)).toBe('#/learn/lesson-2')
    expect(hashToLocation('#/learn/lesson-2')).toEqual(loc)
  })

  it('falls back for empty or unknown hash', () => {
    expect(hashToLocation('')).toEqual(DEFAULT_APP_LOCATION)
    expect(hashToLocation('#/not-a-tab')).toEqual(DEFAULT_APP_LOCATION)
  })

  it('encodes lesson ids with special characters', () => {
    const id = 'custom/course?id=1'
    const hash = locationToHash({ tab: 'learn', lessonId: id })
    expect(hashToLocation(hash).lessonId).toBe(id)
  })
})
