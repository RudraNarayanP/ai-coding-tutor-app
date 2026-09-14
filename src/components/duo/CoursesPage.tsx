import type { CourseSummary } from '../../api'
import { courseShortTitle, isSelectedCourse } from './courseDisplay'

interface CoursesPageProps {
  courses: CourseSummary[]
  selectedLanguage: string
  onSelectCourse: (lang: string) => void
}

export function CoursesPage({ courses, selectedLanguage, onSelectCourse }: CoursesPageProps) {
  return (
    <div className="duo-courses-page">
      <h1 className="duo-courses-heading">Courses</h1>
      {courses.length === 0 ? (
        <p className="duo-empty-note">No courses were returned by the server.</p>
      ) : (
        <div className="duo-courses-grid" role="tablist" aria-label="Course language selector">
          {courses.map((c) => {
            const selected = isSelectedCourse(c, selectedLanguage)
            const label = courseShortTitle(c.title)
            return (
              <button
                key={c.id}
                type="button"
                role="tab"
                aria-selected={selected}
                className={`duo-course-tile ${selected ? 'is-selected' : ''}`}
                onClick={() => onSelectCourse(c.language || c.id)}
              >
                {selected ? <span className="duo-course-check" aria-hidden="true">✓</span> : null}
                <span className="duo-course-tile-flag" aria-hidden="true">
                  {label.slice(0, 2).toUpperCase()}
                </span>
                <span className="duo-course-tile-name">{label}</span>
                <span className="duo-course-tile-meta">
                  {c.completed_count} / {c.lesson_count} lessons
                </span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
