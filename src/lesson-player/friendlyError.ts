import { translatePythonError } from '../utils/pythonErrorTranslator'

function lineNumber(raw: string): string {
  const match = raw.match(/line (\d+)/i)
  return match?.[1] ?? '1'
}

/** Plain-language Python errors. The raw message stays behind a Details toggle. */
export function friendlyPythonError(raw: string): { summary: string; detail: string } {
  const detail = (raw || '').trim()
  if (!detail) return { summary: 'Something went wrong while running your code.', detail: '' }

  const line = lineNumber(detail)
  if (/SyntaxError/i.test(detail) && /expected ':'/i.test(detail)) {
    return { summary: `You're missing a colon on line ${line}`, detail }
  }
  if (/SyntaxError/i.test(detail) && /invalid syntax/i.test(detail)) {
    return { summary: `Python couldn't read line ${line}. Check the spelling and punctuation.`, detail }
  }
  if (/IndentationError/i.test(detail)) {
    return { summary: `Line ${line} needs to line up with the lines around it.`, detail }
  }
  if (/NameError/i.test(detail)) {
    const name = detail.match(/name '([^']+)' is not defined/)?.[1]
    return {
      summary: name
        ? `${name} is used before it exists. Check the spelling.`
        : 'A name is used before it exists. Check the spelling.',
      detail,
    }
  }

  const translated = translatePythonError(detail)
  return {
    summary: translated.summary.replace(/`([^`]+)`/g, '$1'),
    detail,
  }
}
