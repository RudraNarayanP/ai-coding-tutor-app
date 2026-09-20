/**
 * Frontend mirror of `backend/exercise_types.py`.
 *
 * The widget router, the submit payload builder and curriculum validation all
 * need the same type lists. They used to be re-typed in three places, which is
 * how `short_answer` ended up graded by the server but never routed to a widget
 * on the client. `backend/test_exercise_types.py` asserts these arrays match
 * the Python frozensets, so drift fails a test instead of shipping.
 */

export const CHOICE_TYPES: readonly string[] = [
  'mcq',
  'true_false',
  'output_prediction',
  'debugging',
  'identify_error',
  'short_answer',
]

export const MULTI_SELECT_TYPES: readonly string[] = ['select_multiple']
export const ORDERING_TYPES: readonly string[] = ['ordering']
export const MATCHING_TYPES: readonly string[] = ['matching']
export const FILL_TYPES: readonly string[] = ['fill_blank', 'code_completion']
export const CODE_TYPES: readonly string[] = ['code', 'tiny_coding', 'identify_mistake']

/** Types the server recognises. Anything else must not be silently accepted. */
export const ALL_EXERCISE_TYPES: readonly string[] = [
  ...CHOICE_TYPES,
  ...MULTI_SELECT_TYPES,
  ...ORDERING_TYPES,
  ...MATCHING_TYPES,
  ...FILL_TYPES,
  ...CODE_TYPES,
]

/**
 * Backwards-compatible alias. Several widgets key off "is this a tap-a-choice
 * question", and the historical name is kept so existing call sites read the
 * same while pointing at the shared list.
 */
export const MCQ_TYPES: readonly string[] = CHOICE_TYPES

export type ExerciseWidget =
  | 'choice'
  | 'multi_select'
  | 'ordering'
  | 'matching'
  | 'fill'
  | 'code'
  | 'unknown'

export function normaliseType(exType: unknown): string {
  return String(exType ?? '').toLowerCase().trim()
}

export function widgetFor(exType: unknown): ExerciseWidget {
  const type = normaliseType(exType)
  if ((CHOICE_TYPES as readonly string[]).includes(type)) return 'choice'
  if ((MULTI_SELECT_TYPES as readonly string[]).includes(type)) return 'multi_select'
  if ((ORDERING_TYPES as readonly string[]).includes(type)) return 'ordering'
  if ((MATCHING_TYPES as readonly string[]).includes(type)) return 'matching'
  if ((FILL_TYPES as readonly string[]).includes(type)) return 'fill'
  if ((CODE_TYPES as readonly string[]).includes(type)) return 'code'
  return 'unknown'
}

export function isCodeLikeExercise(exType: unknown): boolean {
  const widget = widgetFor(exType)
  return widget === 'code' || widget === 'fill'
}

export function isKnownExerciseType(exType: unknown): boolean {
  return ALL_EXERCISE_TYPES.includes(normaliseType(exType))
}
