import React, { useMemo } from 'react'
import katex from 'katex'
import { parseRichLessonText } from '../utils/parseRichLessonText'
import 'katex/dist/katex.min.css'

type LessonRichTextProps = {
  text: string
  className?: string
  /** Block wrapper for descriptions; inline span for titles or list items. */
  block?: boolean
}

function MathBlock({ tex, display }: { tex: string; display: boolean }) {
  const html = useMemo(() => {
    try {
      return katex.renderToString(tex, {
        throwOnError: false,
        displayMode: display,
        strict: 'ignore',
        trust: false,
      })
    } catch {
      return null
    }
  }, [tex, display])

  if (!html) {
    return <span className="lesson-rich-math lesson-rich-math--fallback">{tex}</span>
  }

  if (display) {
    return (
      <span
        className="lesson-rich-math lesson-rich-math--display"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    )
  }

  return (
    <span
      className="lesson-rich-math lesson-rich-math--inline"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

export function LessonRichText({ text, className, block = false }: LessonRichTextProps) {
  const segments = useMemo(() => parseRichLessonText(text), [text])
  const Tag = block ? 'div' : 'span'

  return (
    <Tag className={['lesson-rich-text', className].filter(Boolean).join(' ')}>
      {segments.map((seg, idx) => {
        if (seg.type === 'text') {
          return <React.Fragment key={idx}>{seg.value}</React.Fragment>
        }
        if (seg.type === 'code') {
          return (
            <code key={idx} className="ew-task-code">
              {seg.value}
            </code>
          )
        }
        return <MathBlock key={idx} tex={seg.value} display={seg.display} />
      })}
    </Tag>
  )
}
