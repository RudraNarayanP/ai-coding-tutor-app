import type { PathLesson } from './LearnPath'
import type { Material, MaterialCompletionResult } from '../../api'
import { MaterialsView } from '../MaterialsView'

interface PracticeHubProps {
  lessons: PathLesson[]
  isLoadingLesson: boolean
  onOpenLesson: (lesson: PathLesson) => void
  onOpenGuidebook: () => void
  materials?: Material[]
  completedMaterialIds?: string[]
  onCompleteMaterial?: (id: string, user_answer?: string) => Promise<MaterialCompletionResult | null>
}

export function PracticeHub({
  lessons,
  isLoadingLesson,
  onOpenLesson,
  onOpenGuidebook,
  materials = [],
  completedMaterialIds = [],
  onCompleteMaterial,
}: PracticeHubProps) {
  const current = lessons.find((l) => l.status === 'current')
  const completed = lessons.filter((l) => l.status === 'completed')
  const lastCompleted = completed.length > 0 ? completed[completed.length - 1] : null
  const practiceLessons = lessons.filter((l) => l.type === 'practice' && l.status !== 'locked')
  const firstPractice = practiceLessons[0] ?? null
  const completedCount = completed.length

  return (
    <div className="duo-learn-stage" style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
      <div>
        <h1 className="duo-page-heading">Today&apos;s Review</h1>

        <div className="duo-hero-card" style={{ marginTop: '16px' }}>
          <div>
            <h2 className="duo-hero-title">Unit Rewind</h2>
            {current ? (
              <p className="duo-hero-copy">Continue your current lesson: {current.title}</p>
            ) : lastCompleted ? (
              <p className="duo-hero-copy">Revisit your last completed lesson: {lastCompleted.title}</p>
            ) : (
              <p className="duo-hero-copy">No current or completed lesson is available to review yet.</p>
            )}
            {current ? (
              <button
                type="button"
                className="duo-button duo-button-primary"
                disabled={isLoadingLesson}
                onClick={() => onOpenLesson(current)}
              >
                START
              </button>
            ) : lastCompleted ? (
              <button
                type="button"
                className="duo-button duo-button-primary"
                disabled={isLoadingLesson}
                onClick={() => onOpenLesson(lastCompleted)}
              >
                REVIEW
              </button>
            ) : (
              <button type="button" className="duo-button duo-button-primary" disabled>
                START — no lesson to review
              </button>
            )}
          </div>
        </div>
      </div>

      <div>
        <h2 className="duo-section-heading">Practice Activities</h2>
        <div className="duo-stack-list" style={{ marginTop: '12px' }}>
          <PracticeRow
            title="Practice lessons"
            detail={
              firstPractice ? `Open ${firstPractice.title}` : 'No unlocked practice lessons in this course'
            }
            enabled={Boolean(firstPractice) && !isLoadingLesson}
            disabledReason="No unlocked practice lessons in this course"
            onClick={() => firstPractice && onOpenLesson(firstPractice)}
          />
          <PracticeRow
            title="Completed lessons"
            detail={
              lastCompleted
                ? `${completedCount} completed — reopen ${lastCompleted.title}`
                : 'Complete a lesson on the Learn path first'
            }
            enabled={Boolean(lastCompleted) && !isLoadingLesson}
            disabledReason="Complete a lesson on the Learn path first"
            onClick={() => lastCompleted && onOpenLesson(lastCompleted)}
          />
          <PracticeRow
            title="Guidebook"
            detail="Open syntax and concept reference for the active course"
            enabled
            onClick={onOpenGuidebook}
          />
        </div>
      </div>

      {/* Materials & Resources Section */}
      {materials.length > 0 && onCompleteMaterial && (
        <div style={{ marginTop: '8px' }}>
          <MaterialsView
            materials={materials}
            completedMaterialIds={completedMaterialIds}
            onCompleteMaterial={onCompleteMaterial}
          />
        </div>
      )}
    </div>
  )
}

function PracticeRow({
  title,
  detail,
  enabled,
  disabledReason,
  onClick,
}: {
  title: string
  detail: string
  enabled: boolean
  disabledReason?: string
  onClick?: () => void
}) {
  return (
    <button
      type="button"
      className={`duo-stack-row ${enabled ? '' : 'is-disabled'}`}
      disabled={!enabled}
      title={!enabled ? disabledReason : undefined}
      onClick={onClick}
    >
      <div>
        <div className="duo-stack-row-title">{title}</div>
        <div className="duo-stack-row-detail">{detail}</div>
      </div>
    </button>
  )
}
