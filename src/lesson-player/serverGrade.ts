import type { Exercise } from './types'

export type ServerGrade = {
  passed: boolean
  explanation: string
  answerLine?: string
}

function oneLine(value: string): string {
  const clean = value.replace(/`([^`]+)`/g, '$1').replace(/\s+/g, ' ').trim()
  if (/traceback|syntaxerror|exception/i.test(clean)) {
    return 'That did not run. Read the result row and try again.'
  }
  const sentence = clean.split(/(?<=[.!?])\s+/)[0] || clean
  return sentence.slice(0, 180)
}

export function payloadFor(exercise: Exercise, draft: string | string[] | null, code: string): Record<string, unknown> {
  const kind = exercise.server?.kind
  if (kind === 'code') return { code }
  if (kind === 'fill') return { answer: typeof draft === 'string' ? draft : '' }
  if (kind === 'order') return { order: Array.isArray(draft) ? draft : [] }
  if (kind === 'multi') return { answers: Array.isArray(draft) ? draft : draft ? [draft] : [] }
  return { answer: typeof draft === 'string' ? draft : '' }
}

export async function gradeOnServer(
  exercise: Exercise,
  draft: string | string[] | null,
  code: string
): Promise<ServerGrade> {
  const server = exercise.server
  if (!server) return { passed: false, explanation: 'This step has no grader.' }
  try {
    const res = await fetch(
      `/api/lessons/${encodeURIComponent(server.lessonId)}/submit-exercise`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          exercise_id: server.exerciseId,
          sublesson_id: server.sublessonId ?? null,
          payload: payloadFor(exercise, draft, code),
        }),
      }
    )
    const data = (await res.json().catch(() => ({}))) as {
      passed?: boolean
      feedback?: string
      explanation?: string
      revealed_answer?: string
    }
    if (!res.ok && data.passed == null) {
      return { passed: false, explanation: 'The checker is offline. Try again in a moment.' }
    }
    const feedback = String(data.feedback || '')
    const expected = data.revealed_answer?.trim() || feedback.match(/Expected:\s*(.+)/i)?.[1]?.trim()
    const why = oneLine(String(data.explanation || feedback || exercise.explanation || 'Try the other choice.'))
    return {
      passed: Boolean(data.passed),
      explanation: why || 'Try the other choice.',
      answerLine: expected,
    }
  } catch {
    return { passed: false, explanation: 'The checker is offline. Try again in a moment.' }
  }
}
