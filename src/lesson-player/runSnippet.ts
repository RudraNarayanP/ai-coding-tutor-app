import { friendlyPythonError } from './friendlyError'
import type { Exercise, RunView, WriteTest } from './types'

const PREVIEW_URL = '/api/lessons/booleans/exercises/player-preview/run'

type PreviewBody = {
  stdout?: string
  stderr?: string
  error?: string | null
  passed?: boolean
}

function harness(code: string, tests: WriteTest[]): string {
  const checks = tests
    .map((test, index) => {
      if ('expectStdout' in test) return ''
      const expr = test.expr
      const expectRepr = test.expectRepr
      return `
try:
    __ok = (${expr}) == ${expectRepr}
    print('__PW_${index}__' + ('1' if __ok else '0'))
except Exception as __exc:
    print('__PW_${index}__E' + type(__exc).__name__ + ': ' + str(__exc))
`
    })
    .join('\n')
  return `${code}\nprint('__PW_SPLIT__')\n${checks}`
}

function plainLabel(value: string): string {
  return value.replace(/`([^`]+)`/g, '$1').replace(/_/g, ' ').replace(/^test /i, '').trim()
}

export async function runServerExercise(lessonId: string, exerciseId: string, code: string): Promise<RunView> {
  const url = exerciseId
    ? `/api/lessons/${encodeURIComponent(lessonId)}/exercises/${encodeURIComponent(exerciseId)}/run`
    : `/api/lessons/${encodeURIComponent(lessonId)}/run`
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    })
    const body = (await res.json().catch(() => ({}))) as {
      tests?: { name?: string; description?: string; passed?: boolean; error?: string | null }[]
      error?: string | null
      stdout?: string
    }
    if (!res.ok) {
      return {
        ran: true,
        errorSummary: 'The code runner is offline. Start the backend and try again.',
        errorDetail: typeof body.error === 'string' ? body.error : 'Request failed',
        tests: [],
      }
    }
    if (body.error && !(body.tests || []).length) {
      const friendly = friendlyPythonError(String(body.error))
      return { ran: true, errorSummary: friendly.summary, errorDetail: friendly.detail, tests: [] }
    }
    const tests = (body.tests || []).map((test, index) => ({
      id: test.name || `test-${index}`,
      label: plainLabel(test.description || test.name || `Test ${index + 1}`),
      passed: Boolean(test.passed),
    }))
    return { ran: true, errorSummary: null, errorDetail: null, tests }
  } catch (err) {
    return {
      ran: true,
      errorSummary: 'The code runner is offline. Start the backend and try again.',
      errorDetail: err instanceof Error ? err.message : 'Network error',
      tests: [],
    }
  }
}

export async function runWriteExercise(exercise: Exercise, code: string): Promise<RunView> {
  if (exercise.server?.kind === 'code') {
    return runServerExercise(exercise.server.lessonId, exercise.server.exerciseId, code)
  }
  const tests = exercise.tests ?? []
  const stdoutOnly = tests.length > 0 && tests.every((test) => 'expectStdout' in test)
  const program = stdoutOnly ? code : harness(code, tests)

  let body: PreviewBody
  try {
    const res = await fetch(PREVIEW_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: program }),
    })
    body = (await res.json().catch(() => ({}))) as PreviewBody
    if (!res.ok) {
      const message = 'The code runner is offline. Start the backend and try again.'
      return {
        ran: true,
        errorSummary: message,
        errorDetail: typeof body.error === 'string' ? body.error : message,
        tests: tests.map((test) => ({ id: test.id, label: test.label, passed: false })),
      }
    }
  } catch (err) {
    const detail = err instanceof Error ? err.message : 'Network error'
    return {
      ran: true,
      errorSummary: 'The code runner is offline. Start the backend and try again.',
      errorDetail: detail,
      tests: tests.map((test) => ({ id: test.id, label: test.label, passed: false })),
    }
  }

  if (body.error) {
    const friendly = friendlyPythonError(String(body.error))
    return {
      ran: true,
      errorSummary: friendly.summary,
      errorDetail: friendly.detail,
      tests: tests.map((test) => ({ id: test.id, label: test.label, passed: false })),
    }
  }

  const stdout = body.stdout ?? ''
  if (stdoutOnly) {
    return {
      ran: true,
      errorSummary: null,
      errorDetail: null,
      tests: tests.map((test) => {
        const expected = 'expectStdout' in test ? test.expectStdout : ''
        const actual = stdout.trim()
        const passed = expected.trim() === '' ? true : actual === expected.trim()
        return { id: test.id, label: test.label, passed }
      }),
    }
  }

  const marker = stdout.split('__PW_SPLIT__')
  const report = marker[1] ?? ''
  const rows = tests.map((test, index) => {
    if ('expectStdout' in test) {
      return { id: test.id, label: test.label, passed: false }
    }
    const token = report.match(new RegExp(`__PW_${index}__([^\\n]*)`))
    const value = token?.[1] ?? ''
    return { id: test.id, label: test.label, passed: value === '1' }
  })

  const exploded = report.match(/__PW_\d+__E([^\n]+)/)
  if (exploded) {
    const friendly = friendlyPythonError(exploded[1])
    return { ran: true, errorSummary: friendly.summary, errorDetail: friendly.detail, tests: rows }
  }

  return { ran: true, errorSummary: null, errorDetail: null, tests: rows }
}
