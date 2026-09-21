/**
 * Shared data-model types for the learning session.
 *
 * These were lifted out of App.tsx unchanged when navigation moved to the
 * router, so the screen components and the session hook can both import them
 * without depending on the App module.
 */

export type TestResult = {
  name: string
  passed: boolean
  required: boolean
  description: string
  error: string | null
}

export const CODE_EXERCISE_TYPES = ['code', 'tiny_coding', 'identify_mistake']
export const FILL_EXERCISE_TYPES = ['fill_blank', 'code_completion']

export type LessonSummary = {
  id: string
  title: string
  order: number
  difficulty: string
  duration_minutes: number
  status: 'completed' | 'current' | 'locked'
  type?: 'learn' | 'practice' | 'checkpoint' | 'challenge'
  section_id?: string
  section_title?: string
  unit_id?: string
  unit_title?: string
  concept_id?: string
  concept_title?: string
  test_out_eligible?: boolean
  xp_reward?: number
}

export type Exercise = {
  id: string
  title?: string
  type: string
  question?: string
  options?: string[]
  correct_answer?: string | string[] | Record<string, string>
  blanks?: string[]
  pairs?: { left: string; right: string }[]
  starter_code?: string
  solution_code?: string
  hints?: string[]
  xp_reward?: number
  explanation?: string
}

export type SubLesson = {
  id: string
  title: string
  description?: string
  order: number
  exercises: Exercise[]
}

// File extensions used by the sandbox for each course track (python-based
// tracks — DSA, ML, AI, Fullstack — execute plain Python).
export const LANGUAGE_FILE_EXT: Record<string, string> = {
  python: 'py', py: 'py', dsa: 'py', ml: 'py', 'ml-math': 'py', ai: 'py',
  fullstack: 'py', javascript: 'js', typescript: 'ts', java: 'java',
  cpp: 'cpp', 'c++': 'cpp', sql: 'sql',
}

/** Neutral editor prompt; anything else in `feedback` is tutor output. */
export const DEFAULT_FEEDBACK = 'Run your code to get immediate feedback from the local sandbox.'

export type Lesson = {
  id: string
  title: string
  description: string
  order: number
  difficulty: string
  duration_minutes: number
  starter_code: string
  type?: 'learn' | 'practice' | 'checkpoint' | 'challenge'
  section_id?: string
  section_title?: string
  unit_id?: string
  unit_title?: string
  concept_id?: string
  concept_title?: string
  test_out_eligible?: boolean
  concepts?: string[]
  prerequisites?: string[]
  learning_objectives?: string[]
  source?: { name: string; url: string; license?: string } | null
  sublessons?: SubLesson[]
  mastery_exam?: Exercise[]
  xp_reward?: number
}

export type ProviderStatus = {
  provider: string
  name: string
  available: boolean
  model: string
  is_current: boolean
  reason: string | null
  error: string | null
}

export type CourseSummary = {
  id: string
  title: string
  language: string
  lesson_count: number
  completed_count: number
}

export type ProvidersOverview = {
  current_provider: string
  providers: ProviderStatus[]
}

/** Which lesson is being fetched, and why the route could not be satisfied. */
export type LessonLoadError = 'not_found' | 'network' | null
