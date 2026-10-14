import type { Exercise } from './types'

export function normalizeSpace(value: string): string {
  return value.trim().replace(/\s+/g, ' ')
}

export function gradeExercise(exercise: Exercise, draft: string | string[] | null): boolean {
  if (exercise.type === 'teach') return true
  if (draft == null) return false

  if (exercise.type === 'tap_to_build') {
    const built = Array.isArray(draft) ? draft.join(' ') : draft
    const expected = Array.isArray(exercise.answer) ? exercise.answer.join(' ') : exercise.answer
    return normalizeSpace(built) === normalizeSpace(expected)
  }

  if (exercise.type === 'write_code') return false

  const expected = Array.isArray(exercise.answer) ? exercise.answer[0] : exercise.answer
  return String(draft).trim() === String(expected).trim()
}

export function hasDraft(exercise: Exercise, draft: string | string[] | null): boolean {
  if (exercise.type === 'teach') return true
  if (draft == null) return false
  if (exercise.type === 'tap_to_build' || exercise.multi) return Array.isArray(draft) && draft.length > 0
  if (exercise.type === 'write_code') {
    return typeof draft === 'string' && draft.trim().length > 0 && !draft.includes('___')
  }
  return typeof draft === 'string' && draft.trim().length > 0
}

/** Wrong answers are re-queued once at the end of the lesson. */
export function enqueueMiss<T extends { id: string }>(queue: T[], exercise: T, already: string[]): {
  queue: T[]
  requeued: string[]
} {
  if (already.includes(exercise.id)) return { queue, requeued: already }
  return { queue: [...queue, exercise], requeued: [...already, exercise.id] }
}
