import React from 'react'

export interface LessonSourceInfo {
  name: string
  url: string
  license?: string
}

interface LessonSourceNoteProps {
  source?: LessonSourceInfo | null
  objectives?: string[]
}

/**
 * Shared lesson attribution block: learning objectives + the real
 * documentation source a lesson was grounded in. Rendered by every lesson
 * surface (ExerciseWorkspace task card, ExercisePanel pass-through) so no
 * course or lesson type is special-cased.
 */
export const LessonSourceNote: React.FC<LessonSourceNoteProps> = ({ source, objectives }) => {
  const cleanObjectives = (objectives || []).filter((o) => String(o).trim())
  if (!source?.url && cleanObjectives.length === 0) return null

  return (
    <div className="lesson-source-note" data-testid="lesson-source-note">
      {cleanObjectives.length > 0 && (
        <div className="lesson-source-objectives">
          <span className="lesson-source-label">You will be able to…</span>
          <ul>
            {cleanObjectives.map((obj, i) => (
              <li key={i}>{obj}</li>
            ))}
          </ul>
        </div>
      )}
      {source?.url && (
        <p className="lesson-source-line">
          <span aria-hidden="true">📖</span> Grounded in{' '}
          <a
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="lesson-source-link"
          >
            {source.name || source.url}
          </a>
          {source.license ? <span className="lesson-source-license"> · {source.license}</span> : null}
        </p>
      )}
    </div>
  )
}

export default LessonSourceNote
