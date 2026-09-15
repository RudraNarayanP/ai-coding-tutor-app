// Learner-facing copy helpers for Create Course only.
// Backend sanitization is the source of truth; this is a last-line defense so a
// persisted caption dump never dominates the workspace UI.

const MAX_BODY = 280
const MAX_QUOTE = 160

const FILLERS = /\b(um+|uh+|you know|kind of|sort of|and so(?: it's)?|going to|gonna|right so|basically|yeah|welcome back)\b/gi

export function isTranscriptDump(text: string | null | undefined, maxLen = MAX_BODY): boolean {
  if (!text) return false
  const t = text.replace(/\s+/g, ' ').trim()
  if (!t) return false
  if (t.length > maxLen) return true
  const fillers = (t.match(FILLERS) || []).length
  const stops = (t.match(/[.!?]/g) || []).length
  return t.length > 160 && stops <= 1 && fillers >= 2
}

export function compactText(text: string | null | undefined, maxLen = MAX_BODY): string {
  if (!text) return ''
  const t = text.replace(/\s+/g, ' ').trim()
  if (!t || isTranscriptDump(t, maxLen)) return ''
  return t
}

export function milestoneDescription(m: {
  source_grounded_description?: string
  teach?: string
  title?: string
}): string {
  return compactText(m.source_grounded_description) || compactText(m.teach) || ''
}

export function whyExplanation(m: { why?: string; title?: string }): string {
  const why = compactText(m.why, 420)
  if (why) return why
  const title = (m.title || '').trim()
  return title
    ? `This step, “${title}”, is part of building the project from the tutorial.`
    : 'This step is part of building the project from the tutorial.'
}

export function sourceExcerpt(quote: string | null | undefined): string {
  return compactText(quote, MAX_QUOTE)
}
