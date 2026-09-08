// ─── Patchwork API layer ──────────────────────────────────────────────────────
// All backend calls are typed through this module. URLs and payload shapes match
// the existing FastAPI backend exactly — the redesign never changes backend contracts.

export type TestResult = {
  name: string
  passed: boolean
  required: boolean
  description: string
  error: string | null
  stdout?: string
  stderr?: string
  execution_time_ms?: number
}

export type ExerciseView = {
  id: string
  title?: string
  type: string
  question?: string
  options?: string[]
  blanks?: string[]
  pairs?: { left: string; right: string }[]
  starter_code?: string
  hints?: string[]
  xp_reward?: number
}

export type SubLessonView = {
  id: string
  title: string
  description?: string
  order: number
  exercises: ExerciseView[]
}

export type LessonView = {
  id: string
  title: string
  description: string
  order: number
  difficulty: string
  duration_minutes: number
  starter_code: string
  type?: string
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
  sublessons?: SubLessonView[]
  mastery_exam?: ExerciseView[]
  xp_reward?: number
}

export type LessonSummary = {
  id: string
  title: string
  order: number
  difficulty: string
  duration_minutes: number
  status: 'completed' | 'current' | 'locked'
  type?: 'learn' | 'practice' | 'checkpoint' | 'challenge' | 'review'
  section_id?: string
  section_title?: string
  unit_id?: string
  unit_title?: string
  concept_id?: string
  concept_title?: string
  test_out_eligible?: boolean
}

export type CourseSummary = {
  id: string
  title: string
  language: string
  lesson_count: number
  completed_count: number
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

export type ProvidersOverview = {
  current_provider: string
  fallback_provider: string | null
  providers: ProviderStatus[]
}

export type TutorResponse = {
  available: boolean
  message: string
  hint_level?: number
  provider?: string
  error?: string | null
}

export type RunResult = {
  lesson_id?: string
  passed: boolean
  completed: boolean
  next_lesson_id?: string | null
  tests: TestResult[]
  stdout?: string
  stderr?: string
  execution_time_ms?: number
  error?: string | null
}

export type ExerciseResult = {
  exercise_id: string
  passed: boolean
  state?: 'correct' | 'incorrect'
  attempt_count?: number
  feedback: string
  xp_awarded: number
  total_xp: number
  level: number
  explanation?: string
  next_action?: 'continue' | 'retry' | 'lesson_complete'
  lesson_completed?: boolean
  next_lesson_id?: string | null
  progress?: { completed: number; total: number }
}

export type LessonProgress = {
  lesson_id: string
  total_exercises: number
  completed_exercise_ids: string[]
  attempt_counts: Record<string, number>
  last_results: Record<string, 'correct' | 'incorrect'>
  lesson_completed: boolean
  next_action: 'answer' | 'lesson_complete'
  next_lesson_id: string | null
  progress: { completed: number; total: number }
}

export type TestOutResult = {
  passed: boolean
  score_pct: number
  passed_count?: number
  total_questions?: number
  xp_awarded: number
  total_xp: number
  level: number
  weak_areas?: string[]
  error?: string
}

export type ProgressionState = {
  completed_lesson_ids: string[]
  mastered_lesson_ids: string[]
  skipped_lesson_ids: string[]
  completed_sublesson_ids: string[]
  completed_exercise_ids: string[]
  current_lesson_id: string | null
  xp: number
  level: number
}

// ─── Small fetch helper ───────────────────────────────────────────────────────

async function request<T>(url: string, opts?: RequestInit): Promise<T | null> {
  try {
    const res = await fetch(url, opts)
    if (!res.ok) return null
    return (await res.json()) as T
  } catch {
    return null
  }
}

function post(url: string, body: unknown): Promise<Response> {
  return fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

// ─── Endpoints ─────────────────────────────────────────────────────────────────

export const api = {
  courses: () => request<CourseSummary[]>('/api/courses'),

  selectCourse: (language: string) =>
    request<{ status?: string }>('/api/courses/select', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ language }),
    }),

  lessons: (language: string) =>
    request<LessonSummary[]>(`/api/lessons?language=${encodeURIComponent(language)}`),

  lesson: (id: string) => request<LessonView>(`/api/lessons/${id}`),

  lessonProgress: (id: string) => request<LessonProgress>(`/api/lessons/${id}/progress`),

  lessonSolution: (id: string) =>
    request<{ solution_code: string }>(`/api/lessons/${id}/solution`),

  runLesson: (id: string, code: string) =>
    fetch(`/api/lessons/${id}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    }),

  submitExercise: (
    id: string,
    exerciseId: string,
    sublessonId: string | undefined,
    payload: Record<string, unknown>
  ) =>
    post(`/api/lessons/${id}/submit-exercise`, {
      exercise_id: exerciseId,
      sublesson_id: sublessonId ?? null,
      payload,
    }),

  testOut: (id: string, submissions: Record<string, Record<string, unknown>>) =>
    post(`/api/lessons/${id}/test-out`, { submissions }),

  providers: () => request<ProvidersOverview>('/api/ai/providers'),

  selectProvider: (provider: string) =>
    post('/api/ai/select', { provider }),

  tutor: (payload: {
    lesson_id: string
    question?: string
    code?: string
    results?: TestResult[] | null
    hint_level: number
    tone?: string
  }) => post('/api/tutor', payload),

  progression: (language: string) =>
    request<ProgressionState>(`/api/progression?language=${encodeURIComponent(language)}`),
}