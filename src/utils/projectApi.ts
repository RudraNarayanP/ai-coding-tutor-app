// ─── Create Course: Guided Project API client ─────────────────────────────────
// Typed client for the isolated Create Course project-workspace endpoints. This
// module is used ONLY by the Create Course experience.

export type Microstep = {
  observation: string
  action: string
  hint: string
}

export type ProjectMilestone = {
  id: string
  order: number
  title: string
  status: 'pending' | 'current' | 'completed'
  source_grounded_description: string
  source_quote: string
  microstep: Microstep
  why: string
  hook: string
  teach: string
  example: string
  celebrate: string
  xp_reward: number
}

export type WorkspaceFile = {
  path: string
  content: string
}

export type ProjectView = {
  course_id: string
  title: string
  language: string
  source_type: string
  source_url: string
  source_summary: string
  project_goal: string
  tech_stack: string[]
  entry_file: string
  milestones: ProjectMilestone[]
  workspace_files: WorkspaceFile[]
  current_milestone_index: number
  completed_milestone_ids: string[]
  xp: number
  completed: boolean
  completion_percent: number
  files_changed: number
}

export type CheckResult = {
  description: string
  passed: boolean
  detail: string
}

export type NextResult = {
  status: 'incomplete' | 'project_complete'
  advanced: { milestone_id: string; title: string; xp_awarded: number; already_completed: boolean }[]
  current_milestone: ProjectMilestone | null
  checks: CheckResult[]
  feedback: string
  stdout: string
  stderr: string
  xp: number
  completion_percent: number
  completed: boolean
  project: ProjectView
}

export type RunResult = {
  ran_ok: boolean
  stdout: string
  stderr: string
  error: string | null
}

export type GuidanceResult = {
  milestone_id: string | null
  observation: string
  action: string
  hint: string
  why: string
  source_quote: string
  suggestion: string | null
  suggestion_note: string
  provider_used: string | null
}

export type ProjectSummary = {
  course_id: string
  title: string
  language: string
  completion_percent: number
  completed: boolean
  milestone_count: number
  updated_at: number
}

const BASE = '/api/create-course/projects'

export class CreateCourseError extends Error {
  errorCode: string
  decision: 'reject' | 'insufficient' | null
  missingInformation: string[]
  nextStep: string
  rejectionReasons: string[]

  constructor(
    message: string,
    opts: {
      errorCode?: string
      decision?: 'reject' | 'insufficient' | null
      missingInformation?: string[]
      nextStep?: string
      rejectionReasons?: string[]
    } = {}
  ) {
    super(message)
    this.name = 'CreateCourseError'
    this.errorCode = opts.errorCode || 'error'
    this.decision = opts.decision ?? null
    this.missingInformation = opts.missingInformation || []
    this.nextStep = opts.nextStep || ''
    this.rejectionReasons = opts.rejectionReasons || []
  }
}

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = `Request failed (${res.status})`
    let errorCode = `http_${res.status}`
    let decision: 'reject' | 'insufficient' | null = null
    let missingInformation: string[] = []
    let nextStep = ''
    let rejectionReasons: string[] = []
    try {
      const body = await res.json()
      const detail = body?.detail
      if (typeof detail === 'string') {
        message = detail
      } else if (detail && typeof detail === 'object') {
        message = detail.message || detail.user_message || detail.error || message
        errorCode = detail.error || errorCode
        if (detail.decision === 'reject' || detail.decision === 'insufficient') {
          decision = detail.decision
        } else if (errorCode === 'source_rejected') {
          decision = 'reject'
        } else if (errorCode === 'source_insufficient' || errorCode === 'ungroundable_source') {
          decision = 'insufficient'
        }
        missingInformation = Array.isArray(detail.missing_information) ? detail.missing_information : []
        nextStep = detail.next_step || ''
        rejectionReasons = Array.isArray(detail.rejection_reasons) ? detail.rejection_reasons : []
      }
    } catch {
      /* ignore */
    }
    throw new CreateCourseError(message, {
      errorCode,
      decision,
      missingInformation,
      nextStep,
      rejectionReasons,
    })
  }
  return (await res.json()) as T
}

function post(path: string, body: unknown): Promise<Response> {
  return fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export const projectApi = {
  create: (payload: { material_type: string; content: string; title: string; filename?: string }) =>
    post(BASE, payload).then((r) => jsonOrThrow<ProjectView>(r)),

  list: () => fetch(BASE).then((r) => jsonOrThrow<ProjectSummary[]>(r)),

  get: (courseId: string) =>
    fetch(`${BASE}/${encodeURIComponent(courseId)}`).then((r) => jsonOrThrow<ProjectView>(r)),

  saveWorkspace: (courseId: string, files: WorkspaceFile[]) =>
    fetch(`${BASE}/${encodeURIComponent(courseId)}/workspace`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ files }),
    }).then((r) => jsonOrThrow<ProjectView>(r)),

  run: (courseId: string, files: WorkspaceFile[], stdin = '') =>
    post(`${BASE}/${encodeURIComponent(courseId)}/run`, { files, stdin }).then((r) => jsonOrThrow<RunResult>(r)),

  next: (courseId: string, files: WorkspaceFile[]) =>
    post(`${BASE}/${encodeURIComponent(courseId)}/next`, { files }).then((r) => jsonOrThrow<NextResult>(r)),

  guidance: (courseId: string, files: WorkspaceFile[], question = '') =>
    post(`${BASE}/${encodeURIComponent(courseId)}/guidance`, { files, question }).then((r) =>
      jsonOrThrow<GuidanceResult>(r)
    ),

  remove: (courseId: string) =>
    fetch(`${BASE}/${encodeURIComponent(courseId)}`, { method: 'DELETE' }).then((r) => jsonOrThrow<unknown>(r)),
}
