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

/** What finishing the checklist is evidence *of*.
 *
 *  The dialog used to say "verified against the source" unconditionally, and a workspace
 *  of `class Value: pass` files earned that sentence: the grader records whether a step
 *  watched the program run or only read the code's shape, and those are different claims
 *  about different things. The counts are optional because projects saved before the
 *  grader distinguished them have no evidence to report.
 */
export function completionClaim(
  summary: { evidence_executed?: number; evidence_structural?: number; evidence_unverified?: number } | null | undefined,
  title = ''
): string {
  const name = title.trim() ? `“${title.trim()}”` : 'The project'
  const executed = summary?.evidence_executed
  const structural = summary?.evidence_structural
  const unverified = summary?.evidence_unverified
  // A project stored before the grader recorded any of this has no evidence either way,
  // and both remaining sentences would be wrong for it: "nothing here ran the program" is
  // false for a transcript route that ended in a real run, and "the program ran" is
  // unfounded for one that never did. So an absent record gets the one claim it can make.
  if (executed === undefined && structural === undefined && unverified === undefined) {
    return `You finished every step of ${name}.`
  }
  if ((unverified ?? 0) > 0) {
    return `You finished every step of ${name}, but it never ran here — the practice sandbox is missing a dependency it needs, so nothing has checked that it works.`
  }
  if ((executed ?? 0) > 0) {
    return `You built ${name} end-to-end, and the program ran.`
  }
  return `You wrote every file ${name} asks for. Every step was checked against your code's shape — that the files, names and imports are there — and nothing here ran the program.`
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
