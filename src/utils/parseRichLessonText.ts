export type RichSegment =
  | { type: 'text'; value: string }
  | { type: 'code'; value: string }
  | { type: 'math'; value: string; display: boolean }

function pushText(segments: RichSegment[], chunk: string) {
  if (chunk) segments.push({ type: 'text', value: chunk })
}

/**
 * Splits lesson copy into plain text, `inline code`, and LaTeX ($...$, $$...$$, \\(...\\), \\[...\\]).
 */
export function parseRichLessonText(input: string): RichSegment[] {
  const segments: RichSegment[] = []
  let i = 0
  let textBuf = ''

  const flushText = () => {
    pushText(segments, textBuf)
    textBuf = ''
  }

  while (i < input.length) {
    if (input.startsWith('$$', i)) {
      flushText()
      const end = input.indexOf('$$', i + 2)
      if (end === -1) {
        textBuf += input.slice(i)
        break
      }
      segments.push({ type: 'math', value: input.slice(i + 2, end).trim(), display: true })
      i = end + 2
      continue
    }

    if (input.startsWith('\\[', i)) {
      flushText()
      const end = input.indexOf('\\]', i + 2)
      if (end === -1) {
        textBuf += input.slice(i)
        break
      }
      segments.push({ type: 'math', value: input.slice(i + 2, end).trim(), display: true })
      i = end + 2
      continue
    }

    if (input.startsWith('\\(', i)) {
      flushText()
      const end = input.indexOf('\\)', i + 2)
      if (end === -1) {
        textBuf += input.slice(i)
        break
      }
      segments.push({ type: 'math', value: input.slice(i + 2, end).trim(), display: false })
      i = end + 2
      continue
    }

    if (input[i] === '`') {
      flushText()
      const end = input.indexOf('`', i + 1)
      if (end === -1) {
        textBuf += input.slice(i)
        break
      }
      segments.push({ type: 'code', value: input.slice(i + 1, end) })
      i = end + 1
      continue
    }

    if (input[i] === '$' && input[i + 1] !== '$') {
      flushText()
      let j = i + 1
      while (j < input.length) {
        if (input[j] === '$' && input[j - 1] !== '\\') break
        j += 1
      }
      if (j >= input.length) {
        textBuf += input.slice(i)
        break
      }
      segments.push({ type: 'math', value: input.slice(i + 1, j).trim(), display: false })
      i = j + 1
      continue
    }

    textBuf += input[i]
    i += 1
  }

  flushText()
  return segments
}
