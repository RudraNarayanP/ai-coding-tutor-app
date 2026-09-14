import type { CourseSummary } from '../../api'

interface QuestsPageProps {
  courses: CourseSummary[]
  selectedLanguage: string
  completedCount: number
  totalCount: number
  xp: number
  level: number
}

export function QuestsPage({
  courses,
  selectedLanguage,
  completedCount,
  totalCount,
  xp,
  level,
}: QuestsPageProps) {
  const selected = courses.find((c) => c.language === selectedLanguage || c.id === selectedLanguage)
  const coursePct = totalCount > 0 ? Math.min(100, Math.round((completedCount / totalCount) * 100)) : 0
  const monthLabel = new Date().toLocaleString(undefined, { month: 'long' })

  return (
    <div className="duo-quests-layout">
      <div className="duo-quests-main">
        <div className="duo-monthly-quest">
          <div className="duo-monthly-kicker">{monthLabel.toUpperCase()}</div>
          <h1 className="duo-monthly-title">{monthLabel} Quest</h1>
          <p className="duo-empty-note duo-empty-note-on-cyan">
            The server does not store lesson completion dates, so a monthly quest cannot be tracked.
          </p>
          <button type="button" className="duo-button duo-button-secondary" disabled>
            Monthly quest unavailable — no completion dates stored
          </button>
        </div>

        <h2 className="duo-section-heading">Course quests</h2>
        <div className="duo-quest-card">
          <div className="duo-quest-item">
            <span className="duo-quest-icon">📘</span>
            <div className="duo-quest-body">
              <div className="duo-quest-name">
                Complete lessons{selected ? ` in ${selected.title}` : ''}
              </div>
              <div className="duo-quest-progress-bg">
                <div className="duo-quest-progress-fill" style={{ width: `${coursePct}%` }} />
              </div>
              <div className="duo-quest-meta">
                {completedCount} / {totalCount}
              </div>
            </div>
          </div>
          <div className="duo-quest-item">
            <span className="duo-quest-icon">⭐</span>
            <div className="duo-quest-body">
              <div className="duo-quest-name">Lifetime XP (from course progression)</div>
              <div className="duo-quest-meta">
                {xp} XP · Level {level}
              </div>
            </div>
          </div>
          <div className="duo-quest-item is-disabled">
            <span className="duo-quest-icon">⚡</span>
            <div className="duo-quest-body">
              <div className="duo-quest-name">Daily XP goal</div>
              <p className="duo-empty-note">Daily XP is not stored on the server, so this quest is disabled.</p>
            </div>
          </div>
          <div className="duo-quest-item is-disabled">
            <span className="duo-quest-icon">⏱️</span>
            <div className="duo-quest-body">
              <div className="duo-quest-name">Time spent learning</div>
              <p className="duo-empty-note">Session time is not stored on the server, so this quest is disabled.</p>
            </div>
          </div>
        </div>
      </div>

      <aside className="duo-quests-side">
        <div className="duo-widget-card">
          <h2 className="duo-widget-title">Badges</h2>
          <p className="duo-empty-note">
            Monthly badges are not stored. Course completion is {completedCount} of {totalCount} lessons
            {selected ? ` in ${selected.title}` : ''}.
          </p>
        </div>
      </aside>
    </div>
  )
}
