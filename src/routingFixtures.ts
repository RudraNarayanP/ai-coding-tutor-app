/**
 * Backend fixtures shared by the routing tests: one mocked `/api` surface with
 * just enough behaviour to exercise navigation — two lessons, one unit, a
 * two-step lesson whose steps grade successfully.
 */

import { vi } from 'vitest'

// ─── Fixtures ────────────────────────────────────────────────────────────────

const courses = [
  {
    id: 'python-foundations',
    title: 'Python Foundations & Automation',
    language: 'python',
    lesson_count: 3,
    completed_count: 0,
  },
]

const lessons = [
  {
    id: 'lesson-1',
    title: 'Hello, World!',
    order: 1,
    difficulty: 'beginner',
    duration_minutes: 5,
    status: 'completed',
    unit_id: 'unit-basics',
    unit_title: 'Unit 1: Talking to the Computer',
    section_title: 'Section 1',
  },
  {
    id: 'lesson-2',
    title: 'Variables',
    order: 2,
    difficulty: 'beginner',
    duration_minutes: 8,
    status: 'current',
    unit_id: 'unit-basics',
    unit_title: 'Unit 1: Talking to the Computer',
    section_title: 'Section 1',
  },
  {
    id: 'lesson-3',
    title: 'Loops',
    order: 3,
    difficulty: 'beginner',
    duration_minutes: 10,
    status: 'locked',
    unit_id: 'unit-basics',
    unit_title: 'Unit 1: Talking to the Computer',
    section_title: 'Section 1',
  },
]

const lessonDetail = {
  id: 'lesson-2',
  title: 'Variables',
  description: 'Create a variable called name.',
  order: 2,
  difficulty: 'beginner',
  duration_minutes: 8,
  starter_code: '# your code\n',
  unit_id: 'unit-basics',
  unit_title: 'Unit 1: Talking to the Computer',
  sublessons: [
    {
      id: 'sub-1',
      title: 'Part 1',
      order: 1,
      exercises: [
        {
          id: 'ex-1',
          type: 'mcq',
          question: 'Which line stores a value?',
          options: ['name = "Ada"', 'print(name)'],
          correct_answer: 'name = "Ada"',
          xp_reward: 10,
        },
        {
          id: 'ex-2',
          type: 'mcq',
          question: 'Which one reads it back?',
          options: ['print(name)', 'name = "Ada"'],
          correct_answer: 'print(name)',
          xp_reward: 10,
        },
        {
          id: 'ex-3',
          type: 'mcq',
          question: 'What does a variable hold?',
          options: ['A value', 'A file'],
          correct_answer: 'A value',
          xp_reward: 10,
        },
      ],
    },
  ],
}

function progressOf(completed: string[]) {
  return {
    lesson_id: 'lesson-2',
    total_exercises: 3,
    completed_exercise_ids: completed,
    attempt_counts: {},
    last_results: {},
    lesson_completed: completed.length >= 3,
    next_action: completed.length >= 3 ? 'lesson_complete' : 'answer',
    next_lesson_id: null,
    progress: { completed: completed.length, total: 3 },
  }
}

// ─── Mock backend ────────────────────────────────────────────────────────────

export function setupFetch() {
  /** Steps graded correct so far; drives both progress and the submit result. */
  const completed: string[] = []

  const respond = (body: unknown, ok = true, status = 200): Response =>
    ({
      ok,
      status,
      json: () => Promise.resolve(body),
    }) as unknown as Response

  vi.stubGlobal('fetch', vi.fn((url: string, opts?: RequestInit) => {
    const method = opts?.method ?? 'GET'

    if (method === 'POST' && url.includes('/submit-exercise')) {
      const exerciseId = JSON.parse(String(opts?.body)).exercise_id
      if (!completed.includes(exerciseId)) completed.push(exerciseId)
      return Promise.resolve(respond({
        exercise_id: exerciseId,
        passed: true,
        feedback: 'Correct!',
        xp_awarded: 10,
        total_xp: 10,
        level: 1,
        attempt_count: 1,
        lesson_completed: completed.length >= 3,
        next_lesson_id: null,
        progress: progressOf(completed),
        hearts: { hearts: 5, max_hearts: 5, unlimited: false, seconds_to_next_heart: 0 },
      }))
    }
    if (url.includes('/api/courses/select')) return Promise.resolve(respond({ status: 'ok' }))
    if (url.includes('/api/settings')) {
      return Promise.resolve(respond({
        current_provider: 'ollama',
        providers: [
          { id: 'ollama', name: 'Ollama', model: 'llama3.1:8b', base_url: 'http://localhost:11434', api_key_masked: null, available: false, is_local: true },
        ],
      }))
    }
    if (url.includes('/api/courses')) return Promise.resolve(respond(courses))
    if (url.includes('/api/lessons?language=')) return Promise.resolve(respond(lessons))
    if (url.includes('/api/ai/providers')) {
      return Promise.resolve(respond({ current_provider: 'ollama', providers: [] }))
    }
    if (url.includes('/api/progression')) return Promise.resolve(respond({ xp: 0, level: 1 }))
    if (url.includes('/api/user/profile')) {
      return Promise.resolve(respond({ user_id: 'u', username: 'Rudra', level: 1, streak: 0, is_demo: false }))
    }
    if (url.includes('/api/hearts')) {
      return Promise.resolve(respond({ hearts: 5, max_hearts: 5, unlimited: false, seconds_to_next_heart: 0 }))
    }
    if (url.includes('/api/mistakes')) return Promise.resolve(respond({ due: [] }))
    if (url.includes('/api/materials')) return Promise.resolve(respond([]))
    if (url.includes('/api/leaderboard')) return Promise.resolve(respond([]))

    const progressMatch = url.match(/\/api\/lessons\/([^/]+)\/progress$/)
    if (progressMatch) return Promise.resolve(respond(progressOf(completed)))

    const lessonMatch = url.match(/\/api\/lessons\/([^/?]+)$/)
    if (lessonMatch) {
      const id = decodeURIComponent(lessonMatch[1])
      if (id === 'lesson-1' || id === 'lesson-3') {
        // A lesson with no steps of its own: one open-ended code task, which is
        // how most of Patchwork's curriculum is shaped.
        return Promise.resolve(respond({
          id,
          title: id === 'lesson-1' ? 'Hello, World!' : 'Loops',
          description: 'Write the code and run it.',
          order: id === 'lesson-1' ? 1 : 3,
          difficulty: 'beginner',
          duration_minutes: 5,
          starter_code: '# your code\n',
          unit_id: 'unit-basics',
          unit_title: 'Unit 1: Talking to the Computer',
          sublessons: [],
        }))
      }
      if (id !== 'lesson-2') {
        // The backend's real answer for an id it does not know.
        return Promise.resolve(respond({ detail: { error: 'lesson_not_found' } }, false, 404))
      }
      return Promise.resolve(respond(lessonDetail))
    }

    return Promise.resolve(respond({}))
  }))
}

