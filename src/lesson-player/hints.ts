import type { RichPart } from './types'

function plain(parts: RichPart[]): string {
  return parts
    .map((part) => ('code' in part ? part.code : part.text))
    .join('')
    .slice(0, 400)
}

function firstSentences(text: string, max: number): string {
  const bits = text
    .replace(/\s+/g, ' ')
    .split(/(?<=[.!?])\s+/)
    .filter(Boolean)
  return bits.slice(0, max).join(' ')
}

/** Authored hints always work. Ollama may rewrite the first two when it is up. */
export async function resolveHint(
  authored: string,
  level: number,
  lesson: { id: string; title: string },
  prompt: RichPart[]
): Promise<string> {
  if (level >= 3) return authored
  try {
    const health = await fetch('/api/health/ollama', { signal: AbortSignal.timeout(800) })
    if (!health.ok) return authored
    const status = (await health.json()) as { available?: boolean }
    if (!status.available) return authored
    const res = await fetch('/api/tutor', {
      signal: AbortSignal.timeout(1200),
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        lesson_id: lesson.id,
        lesson_title: lesson.title,
        instructions: `Rewrite this coding hint as one short sentence for a beginner. Keep the same meaning. Hint: ${authored}. Task: ${plain(prompt)}`,
        code: '',
        test_results: [],
        previous_hints: [],
        hint_level: Math.min(3, Math.max(1, level)),
      }),
    })
    if (!res.ok) return authored
    const data = (await res.json()) as { available?: boolean; message?: string }
    if (!data.available || !data.message?.trim()) return authored
    return firstSentences(data.message.trim(), 2)
  } catch {
    return authored
  }
}
