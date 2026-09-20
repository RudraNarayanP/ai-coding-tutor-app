export type Material = {
  id: string
  title: string
  description: string
  language: string
  category: string
  difficulty: string
  resource_type: string
  url: string
  official_or_community: string
  estimated_minutes: number
  concept_tags: string[]
  recommended_stage: string
  xp_reward: number
  completion_type: string
  source_domain: string
  is_external: boolean
  is_interactive: boolean
  is_project: boolean
  is_reference: boolean
  is_visualizer: boolean
  is_challenge: boolean
  companion_question?: {
    question: string
    options: string[]
    correct_answer: string
    explanation?: string
  }
}

export type MaterialCompletionResult = {
  material_id: string
  passed: boolean
  feedback: string
  xp_awarded: number
  total_xp: number
}

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
  xp_reward?: number
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
  next_action?: 'answer' | 'review' | 'continue' | 'retry' | 'lesson_complete'
  lesson_completed?: boolean
  lesson_mastered?: boolean
  mastery?: MasteryState
  /** True when this attempt cleared the item from the mistake queue. */
  graduated?: boolean
  still_queued?: boolean
  /** Authoritative pool after this attempt (charged on a miss, refunded on a graduation). */
  hearts?: HeartStatus
  next_lesson_id?: string | null
  progress?: { completed: number; total: number }
}

export type MasteryState = {
  required: number
  cleared: number
  first_attempt_accuracy: number
  threshold: number
  mastered: boolean
}

export type LessonProgress = {
  lesson_id: string
  total_exercises: number
  completed_exercise_ids: string[]
  attempt_counts: Record<string, number>
  last_results: Record<string, 'correct' | 'incorrect'>
  lesson_completed: boolean
  lesson_mastered?: boolean
  mastery?: MasteryState
  cleared_exercise_ids?: string[]
  queued_exercise_ids?: string[]
  next_action: 'answer' | 'review' | 'lesson_complete'
  next_lesson_id: string | null
  progress: { completed: number; total: number }
}

/** One missed exercise waiting to be re-served, as returned by /api/mistakes. */
export type MistakeItem = {
  language: string
  lesson_id: string
  lesson_title: string
  sublesson_id: string | null
  exercise_id: string
  wrong_count: number
  streak: number
  exercise: Record<string, unknown>
}

/** Server-owned heart pool. */
export type HeartStatus = {
  hearts: number
  max_hearts: number
  unlimited: boolean
  seconds_to_next_heart: number
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

export type LeaderboardEntry = {
  rank: number
  user_id: string
  username: string
  xp: number
  level: number
  streak: number
  is_demo: boolean
  is_current_user: boolean
}

export type UserProfile = {
  user_id: string
  username: string
  xp: number
  level: number
  streak: number
  is_demo: boolean
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

/** POST that returns a parsed body, or null when the request failed. */
async function jsonPost<T>(url: string, body: unknown): Promise<T | null> {
  try {
    const res = await post(url, body)
    if (!res.ok) return null
    return (await res.json()) as T
  } catch {
    return null
  }
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

  /** Exercises the learner got wrong, ready to be re-served. */
  mistakes: (language?: string) =>
    request<{ due: MistakeItem[] }>(
      `/api/mistakes?limit=20${language ? `&language=${encodeURIComponent(language)}` : ''}`
    ),

  hearts: () => request<HeartStatus>('/api/hearts'),

  setHeartSettings: (body: { unlimited?: boolean; max_hearts?: number }) =>
    jsonPost<HeartStatus>('/api/hearts/settings', body),

  refillHearts: () => jsonPost<HeartStatus>('/api/hearts/refill', {}),

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
    lesson_title: string
    unit_title?: string
    concept_title?: string
    prerequisites?: string[]
    instructions: string
    code?: string
    test_results: TestResult[]
    previous_hints?: string[]
    hint_level: number
    session_id?: string
    user_id?: string
  }) => post('/api/tutor', payload),

  progression: (language: string) =>
    request<ProgressionState>(`/api/progression?language=${encodeURIComponent(language)}`),

  leaderboard: (userId: string = 'default_user') =>
    request<LeaderboardEntry[]>(`/api/leaderboard?user_id=${encodeURIComponent(userId)}`),

  userProfile: (userId: string = 'default_user') =>
    request<UserProfile>(`/api/user/profile?user_id=${encodeURIComponent(userId)}`),

  updateUserProfile: (payload: { user_id?: string; username?: string; streak?: number; xp?: number }) =>
    post('/api/user/profile', payload),

  submitFeedback: (payload: {
    exercise_id: string
    lesson_id?: string | null
    rating: 'too_easy' | 'too_difficult' | 'report'
    comment?: string
    user_id?: string
  }) => {
    const { user_id, ...body } = payload
    return post(`/api/feedback?user_id=${encodeURIComponent(user_id || 'default_user')}`, body)
  },

  feedbackSummary: (userId: string = 'default_user') =>
    request<{
      user_id: string
      bias: 'easier' | 'harder' | 'balanced'
      too_easy: number
      too_difficult: number
      reports: number
      total: number
    }>(`/api/feedback/summary?user_id=${encodeURIComponent(userId)}`),

  materials: (language?: string, stage?: string) => {
    const params = new URLSearchParams()
    if (language) params.append('language', language)
    if (stage) params.append('stage', stage)
    const query = params.toString()
    return request<Material[]>(`/api/materials${query ? `?${query}` : ''}`)
  },

  completeMaterial: (id: string, user_answer?: string) =>
    request<MaterialCompletionResult>(`/api/materials/${encodeURIComponent(id)}/complete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_answer }),
    }),
}