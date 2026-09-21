/**
 * The route map, in one place, so nothing hard-codes a path string.
 *
 * The entities are Patchwork's own: a course is a `CourseSummary.id` (e.g.
 * `python-foundations`), a unit is the curriculum module id the backend already
 * reports as `unit_id` (e.g. `linear-regression`), and lesson ids are globally
 * unique across tracks (`py-aiml-01`, `linreg-mse`) — `/api/lessons/{id}`
 * resolves a lesson across every course, so a lesson URL needs no course prefix
 * to stay shareable.
 */

/** Which chrome the layout should draw for a pathname. Replaces `activeTab`. */
export type AppView =
  | 'learn'
  | 'lesson'
  | 'courses'
  | 'practice'
  | 'quests'
  | 'create'
  | 'leaderboards'
  | 'profile'
  | 'not-found'

const VIEWS: [RegExp, AppView][] = [
  [/^\/learn(\/|$)/, 'learn'],
  [/^\/course(\/|$)/, 'learn'],
  [/^\/lesson(\/|$)/, 'lesson'],
  [/^\/courses(\/|$)/, 'courses'],
  [/^\/practice(\/|$)/, 'practice'],
  [/^\/quests(\/|$)/, 'quests'],
  [/^\/create(\/|$)/, 'create'],
  [/^\/leaderboards(\/|$)/, 'leaderboards'],
  [/^\/profile(\/|$)/, 'profile'],
]

export function viewFromPathname(pathname: string): AppView {
  for (const [pattern, view] of VIEWS) if (pattern.test(pathname)) return view
  return 'not-found'
}

export const learnPath = () => '/learn'

export const coursesPath = () => '/courses'

export const questsPath = () => '/quests'

export const createPath = () => '/create'

export const leaderboardsPath = () => '/leaderboards'

export const profilePath = () => '/profile'

export const coursePath = (courseId: string) => `/course/${encodeURIComponent(courseId)}`

export const unitPath = (courseId: string, unitId: string) =>
  `${coursePath(courseId)}/unit/${encodeURIComponent(unitId)}`

export const lessonPath = (lessonId: string) => `/lesson/${encodeURIComponent(lessonId)}`

export const exercisePath = (lessonId: string, exerciseId: string) =>
  `${lessonPath(lessonId)}/exercise/${encodeURIComponent(exerciseId)}`

export const practicePath = (activity?: string) =>
  activity ? `/practice/${encodeURIComponent(activity)}` : '/practice'

/** PracticeHub's own card ids; `/practice/:activity` accepts exactly these. */
export const PRACTICE_ACTIVITIES = [
  'mistakes',
  'rewind',
  'practice',
  'completed',
  'guidebook',
  'resources',
] as const

export type PracticeActivity = (typeof PRACTICE_ACTIVITIES)[number]

/**
 * `/review` is the spec's name for the mistake-queue session. PracticeHub already
 * calls that card `mistakes`, so this redirects onto the real activity id rather
 * than inventing a second one.
 */
export const reviewPath = () => practicePath('mistakes')
