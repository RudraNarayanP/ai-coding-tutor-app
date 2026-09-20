const BLANK_TOKEN = '___'

function sanitizeBlankAnswer(answer: string): string {
  if (answer.trim() === BLANK_TOKEN) return ''
  return answer.split(BLANK_TOKEN).join('')
}

function stripQuotes(value: string): string {
  const t = value.trim()
  if ((t.startsWith('"') && t.endsWith('"')) || (t.startsWith("'") && t.endsWith("'"))) {
    return t.slice(1, -1)
  }
  return t
}

/**
 * Build an inline-blank code template from curriculum fill_blank exercises.
 * Native exercises often store the solved code in starter_code and the blank
 * answers in blanks[] without ___ markers in the template.
 */
export function buildFillBlankTemplate(
  starterCode: string,
  blanks?: string[],
  question?: string
): string {
  const code = (starterCode || '').trim()

  if (code.includes(BLANK_TOKEN)) return code

  if (!code && question) {
    const codeLine = question
      .split('\n')
      .map((line) => line.trim())
      .find((line) => line.includes(BLANK_TOKEN))
    if (codeLine) {
      const stripped = codeLine.replace(/^[^:]+:\s*/, '').trim()
      return stripped.replace(/\s*\([^)]*\)\s*$/, '').trim()
    }
    const inline = question.match(/[`']([^`']*`___`[^`']*)[`']/)
    if (inline?.[1]) return inline[1]
  }

  const blankValues = blanks?.filter(Boolean) ?? []
  if (!code) {
    if (blankValues.length > 0) {
      return blankValues.map(() => BLANK_TOKEN).join('\n')
    }
    return BLANK_TOKEN
  }

  let template = code
  for (const blank of blankValues) {
    const candidates = [
      blank,
      stripQuotes(blank),
      `"${stripQuotes(blank)}"`,
      `'${stripQuotes(blank)}'`,
    ]
    const uniqueCandidates = [...new Set(candidates.filter(Boolean))]

    let replaced = false
    for (const candidate of uniqueCandidates) {
      const lastIdx = template.lastIndexOf(candidate)
      if (lastIdx >= 0) {
        template =
          template.slice(0, lastIdx) + BLANK_TOKEN + template.slice(lastIdx + candidate.length)
        replaced = true
        break
      }
    }
    if (!replaced) {
      template += `\n${BLANK_TOKEN}`
    }
  }

  if (!template.includes(BLANK_TOKEN)) {
    template += `\n${BLANK_TOKEN}`
  }

  return template
}

export function assembleFillBlankCode(template: string, answers: string[]): string {
  const parts = template.split(BLANK_TOKEN)
  let assembled = ''
  for (let i = 0; i < parts.length; i++) {
    assembled += parts[i]
    if (i < parts.length - 1) {
      assembled += answers[i] ?? ''
    }
  }
  return assembled
}

export function blankCount(template: string): number {
  if (!template.includes(BLANK_TOKEN)) return 0
  return template.split(BLANK_TOKEN).length - 1
}

export function extractAnswersFromEdited(template: string, edited: string): string[] {
  const parts = template.split(BLANK_TOKEN)
  if (parts.length < 2) return [sanitizeBlankAnswer(edited.trim())]

  const answers: string[] = []
  let pos = 0
  for (let i = 0; i < parts.length - 1; i++) {
    const prefix = parts[i]
    if (!edited.slice(pos).startsWith(prefix)) {
      return [sanitizeBlankAnswer(edited.trim())]
    }
    pos += prefix.length
    const suffix = parts[i + 1]
    if (i === parts.length - 2) {
      answers.push(edited.slice(pos))
      break
    }
    const endIdx = edited.indexOf(suffix, pos)
    if (endIdx < 0) {
      answers.push(edited.slice(pos))
      break
    }
    answers.push(edited.slice(pos, endIdx))
    pos = endIdx
  }
  return answers.map(sanitizeBlankAnswer)
}

export function allBlanksFilled(template: string, answers: string[]): boolean {
  const needed = blankCount(template)
  if (needed === 0) return true
  if (answers.length < needed) return false
  return answers.slice(0, needed).every((answer) => {
    const trimmed = answer.trim()
    return trimmed.length > 0 && trimmed !== BLANK_TOKEN && !trimmed.includes(BLANK_TOKEN)
  })
}

export function isFillBlankCodeComplete(template: string, edited: string): boolean {
  if (!edited.trim()) return false
  if (edited.includes(BLANK_TOKEN)) return false
  if (!template.includes(BLANK_TOKEN)) return true
  const answers = extractAnswersFromEdited(template, edited)
  return allBlanksFilled(template, answers)
}
