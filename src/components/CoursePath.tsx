import React from 'react'
import type { LessonSummary } from '../api'

// Maps lesson status + type to a visual state the CSS can render.
function nodeVariant(lesson: LessonSummary): string {
  if (lesson.status === 'completed') return 'completed'
  if (lesson.status === 'current') return 'current'
  if (lesson.status === 'locked') return 'locked'
  return 'locked'
}

interface CoursePathProps {
  lessons: LessonSummary[]
  activeLessonId: string | null
  completedCount: number
  totalCount: number
  pathTitle: string
  onSelectLesson: (id: string) => void
}

// ─── CoursePath ──────────────────────────────────────────────────────────────
// The centerpiece of the redesign: a vertical journey of connected nodes instead
// of a flat list. Each node is still a real <button> so screen readers and the
// test suite see a standard navigation landmark with labelled buttons.
//
// Accessibility contract (also asserted by tests):
//   <nav aria-label="Lessons"> containing one <button> per lesson, with an
//   accessible name of "${title} — ${status}" and aria-current="page" on the
//   active lesson. Locked lessons are disabled buttons.

export const CoursePath: React.FC<CoursePathProps> = ({
  lessons,
  activeLessonId,
  completedCount,
  totalCount,
  pathTitle,
  onSelectLesson,
}) => {
  const progressPct = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0

  // Human-friendly status label for the accessible name.
  const statusLabel = (lesson: LessonSummary): string => {
    switch (lesson.status) {
      case 'completed':
        return 'Completed'
      case 'current':
        return 'Current lesson'
      default:
        return 'Locked'
    }
  }

  const progressNow = completedCount > 0 ? completedCount : 0

  return (
    <section className="course-path" aria-label="Course path">
      <header className="course-path-header">
        <div className="course-path-title">{pathTitle}</div>
      </header>

      {/* Progress indicator — reuses ARIA progressbar so the test suite can find it */}
      <div
        className="course-progress"
        role="progressbar"
        aria-label="Course progress"
        aria-valuenow={progressNow}
        aria-valuemin={0}
        aria-valuemax={totalCount}
      >
        <div className="course-progress-fill" style={{ width: `${progressPct}%` }} />
        <span className="course-progress-label">
          {completedCount} / {totalCount}
        </span>
      </div>

      {/* The journey — a vertical line of connected nodes */}
      <nav aria-label="Lessons" className="lesson-nav">
        <div className="lesson-nav-line" aria-hidden="true" />
        {lessons.map((lesson) => {
          const variant = nodeVariant(lesson)
          const isActive = lesson.id === activeLessonId
          return (
            <button
              key={lesson.id}
              type="button"
              className={`lesson-node lesson-node--${variant}${isActive ? ' is-active' : ''}`}
              aria-current={isActive ? 'page' : undefined}
              aria-label={`${lesson.title} — ${statusLabel(lesson)}`}
              disabled={lesson.status === 'locked'}
              onClick={() => onSelectLesson(lesson.id)}
            >
              <span className="lesson-node-dot" aria-hidden="true">
                {variant === 'completed' && (
                  <svg viewBox="0 0 20 20" width="14" height="14" fill="none">
                    <path d="M4 10l4 4 8-8" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
                {variant === 'current' && <span className="lesson-node-pulse" />}
                {variant === 'locked' && (
                  <svg viewBox="0 0 20 20" width="12" height="12" fill="none">
                    <rect x="4" y="9" width="12" height="8" rx="2" stroke="currentColor" strokeWidth="1.8" />
                    <path d="M6 9V6a4 4 0 018 0v3" stroke="currentColor" strokeWidth="1.8" />
                  </svg>
                )}
              </span>
              <span className="lesson-node-label">{lesson.title}</span>
            </button>
          )
        })}
      </nav>
    </section>
  )
}