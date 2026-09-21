/**
 * Shown for any route that does not name a real entity: an unknown path, a
 * lesson id the server has never heard of, an unknown course, or a practice
 * activity that is not one of the hub's cards.
 *
 * Reuses the app's existing alert vocabulary rather than inventing a new screen —
 * the point is to fail quietly and stay navigable, never to blank the page. The
 * learner keeps the sidebar, header and hearts, so one bad URL ends a lookup and
 * not the session.
 */

import { useLocation, useNavigate } from 'react-router-dom'
import { useLearning } from '../learning/useLearning'
import { coursesPath, learnPath } from '../learning/routes'

export function NotFoundScreen() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const { lesson, safeLessons } = useLearning()

  // `replace` so the dead address does not stay in history: Back from the map
  // should move on past a URL that failed, not return to it.
  const go = (path: string) => navigate(path, { replace: true })

  return (
    <div className="duo-page-container">
      <div
        className="backend-error-banner"
        role="alert"
        style={{
          background: '#fee2e2',
          color: '#991b1b',
          padding: '24px',
          fontWeight: 700,
          margin: '24px',
          borderRadius: '12px',
        }}
      >
        <p style={{ fontSize: '16px', marginBottom: '8px' }}>
          Nothing here matches that address.
        </p>
        <p style={{ fontWeight: 600, fontSize: '14px', opacity: 0.85 }}>
          <code>{pathname}</code> does not name a lesson, unit or course that exists
          {lesson ? ` — the last lesson you opened was “${lesson.title}”` : ''}. Check the
          address, or pick a course from the Courses page.
        </p>
        <div style={{ display: 'flex', gap: '12px', marginTop: '16px' }}>
          <button className="duo-button duo-button-primary" onClick={() => go(learnPath())}>
            Back to my learning map
          </button>
          <button className="duo-button duo-button-secondary" onClick={() => go(coursesPath())}>
            Browse courses
          </button>
        </div>
      </div>
      <p className="duo-empty-note">
        {safeLessons.length === 0
          ? 'No lessons are loaded for this course yet.'
          : `${safeLessons.length} lesson${safeLessons.length === 1 ? '' : 's'} ready in this course.`}
      </p>
    </div>
  )
}
