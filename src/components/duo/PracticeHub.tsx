import { useMemo, useState } from 'react'
import type { PathLesson } from './LearnPath'
import type { Material, MaterialCompletionResult, MistakeItem } from '../../api'
import { MaterialsView } from '../MaterialsView'
import { fileIcon, slugFilename } from '../../utils/languageFile'

type ActivityId = 'mistakes' | 'rewind' | 'practice' | 'completed' | 'guidebook' | 'resources'

interface PracticeHubProps {
  lessons: PathLesson[]
  isLoadingLesson: boolean
  onOpenLesson: (lesson: PathLesson) => void
  onOpenGuidebook: () => void
  onBack?: () => void
  materials?: Material[]
  completedMaterialIds?: string[]
  onCompleteMaterial?: (id: string, user_answer?: string) => Promise<MaterialCompletionResult | null>
  /** Missed exercises the server wants re-served; empty when nothing is due. */
  mistakes?: MistakeItem[]
  /** Active course id or language, so the file tab never claims `.py` in JS. */
  language?: string
}

function lessonFilename(lesson: PathLesson | null, language?: string): string {
  return slugFilename(lesson?.title || '', language, 'practice')
}

export function PracticeHub({
  lessons,
  isLoadingLesson,
  onOpenLesson,
  onOpenGuidebook,
  onBack,
  materials = [],
  completedMaterialIds = [],
  onCompleteMaterial,
  mistakes = [],
  language,
}: PracticeHubProps) {
  const current = lessons.find((l) => l.status === 'current')
  const completed = lessons.filter((l) => l.status === 'completed')
  const lastCompleted = completed.length > 0 ? completed[completed.length - 1] : null
  const practiceLessons = lessons.filter((l) => l.type === 'practice' && l.status !== 'locked')
  const firstPractice = practiceLessons[0] ?? null
  const completedCount = completed.length
  const progressPct = lessons.length > 0 ? (completedCount / lessons.length) * 100 : 0
  const showResources = materials.length > 0 && Boolean(onCompleteMaterial)

  // The queue is server-owned: an exercise is due when the learner missed it
  // and has not yet re-solved it twice. Opening the owning lesson reuses the
  // normal submit path, which is what drains the queue.
  const topMistake = mistakes.length > 0 ? mistakes[0] : null
  const mistakeLesson = topMistake
    ? lessons.find((l) => l.id === topMistake.lesson_id) ?? null
    : null
  const mistakesEnabled = Boolean(mistakeLesson) && !isLoadingLesson

  const rewindLesson = current ?? lastCompleted ?? null
  const rewindEnabled = Boolean(rewindLesson) && !isLoadingLesson
  const practiceEnabled = Boolean(firstPractice) && !isLoadingLesson
  const completedEnabled = Boolean(lastCompleted) && !isLoadingLesson

  const [activity, setActivity] = useState<ActivityId>(mistakes.length > 0 ? 'mistakes' : 'rewind')
  const [selectedPractice, setSelectedPractice] = useState<PathLesson | null>(firstPractice)
  const [selectedCompleted, setSelectedCompleted] = useState<PathLesson | null>(lastCompleted)

  const activePractice = selectedPractice && practiceLessons.some((l) => l.id === selectedPractice.id)
    ? selectedPractice
    : firstPractice
  const activeCompleted = selectedCompleted && completed.some((l) => l.id === selectedCompleted.id)
    ? selectedCompleted
    : lastCompleted

  const rewindCopy = current
    ? `Continue your current lesson: ${current.title}`
    : lastCompleted
      ? `Revisit your last completed lesson: ${lastCompleted.title}`
      : 'No current or completed lesson is available to review yet.'

  const steps = useMemo(
    () => [
      ...(mistakes.length > 0
        ? [
            {
              id: 'mistakes' as const,
              title: 'Review your misses',
              detail: `${mistakes.length} step${mistakes.length === 1 ? '' : 's'} you got wrong ${
                mistakes.length === 1 ? 'once' : 'at least once'
              } — clear them to make them stick`,
              enabled: mistakesEnabled,
              disabledReason: mistakeLesson
                ? undefined
                : 'The lesson that owns the missed step is no longer available',
            },
          ]
        : []),
      {
        id: 'rewind' as const,
        title: 'Unit Rewind',
        detail: rewindCopy,
        enabled: rewindEnabled,
        disabledReason: 'No unlocked lesson is available to review yet',
      },
      {
        id: 'practice' as const,
        title: 'Practice lessons',
        detail: firstPractice
          ? `Open ${firstPractice.title}`
          : 'No unlocked practice lessons in this course',
        enabled: practiceEnabled,
        disabledReason: 'No unlocked practice lessons in this course',
      },
      {
        id: 'completed' as const,
        title: 'Completed lessons',
        detail: lastCompleted
          ? `${completedCount} completed — reopen ${lastCompleted.title}`
          : 'Complete a lesson on the Learn path first',
        enabled: completedEnabled,
        disabledReason: 'Complete a lesson on the Learn path first',
      },
      {
        id: 'guidebook' as const,
        title: 'Guidebook',
        detail: 'Open syntax and concept reference for the active course',
        enabled: true,
        disabledReason: undefined,
      },
      ...(showResources
        ? [
            {
              id: 'resources' as const,
              title: 'Learning resources',
              detail: `${materials.length} curated resource${materials.length === 1 ? '' : 's'} for this course`,
              enabled: true,
              disabledReason: undefined,
            },
          ]
        : []),
    ],
    [
      completedCount,
      completedEnabled,
      firstPractice,
      lastCompleted,
      materials.length,
      practiceEnabled,
      rewindCopy,
      rewindEnabled,
      showResources,
      mistakes.length,
      mistakesEnabled,
      mistakeLesson,
    ]
  )

  const primary = (() => {
    if (activity === 'rewind') {
      if (current) {
        return {
          label: isLoadingLesson ? 'LOADING…' : 'START',
          enabled: rewindEnabled,
          run: () => rewindLesson && onOpenLesson(rewindLesson),
        }
      }
      if (lastCompleted) {
        return {
          label: isLoadingLesson ? 'LOADING…' : 'REVIEW',
          enabled: rewindEnabled,
          run: () => rewindLesson && onOpenLesson(rewindLesson),
        }
      }
      return { label: 'START — no lesson to review', enabled: false, run: () => undefined }
    }
    if (activity === 'mistakes') {
      return {
        label: isLoadingLesson ? 'LOADING…' : 'RETRY NOW',
        enabled: mistakesEnabled,
        run: () => mistakeLesson && onOpenLesson(mistakeLesson),
      }
    }
    if (activity === 'practice') {
      return {
        label: isLoadingLesson ? 'LOADING…' : 'START',
        enabled: practiceEnabled,
        run: () => activePractice && onOpenLesson(activePractice),
      }
    }
    if (activity === 'completed') {
      return {
        label: isLoadingLesson ? 'LOADING…' : 'REVIEW',
        enabled: completedEnabled,
        run: () => activeCompleted && onOpenLesson(activeCompleted),
      }
    }
    if (activity === 'guidebook') {
      return { label: 'OPEN', enabled: true, run: onOpenGuidebook }
    }
    return null
  })()

  const filename =
    activity === 'mistakes'
      ? lessonFilename(mistakeLesson, language)
      : activity === 'rewind'
      ? lessonFilename(rewindLesson, language)
      : activity === 'practice'
        ? lessonFilename(activePractice, language)
        : activity === 'completed'
          ? lessonFilename(activeCompleted, language)
          : activity === 'guidebook'
            ? 'guidebook.md'
            : 'resources.md'

  const sessionTitle =
    activity === 'mistakes'
      ? `Review your misses: ${mistakes.length} queued`
      : activity === 'rewind'
      ? current
        ? `Continue: ${current.title}`
        : lastCompleted
          ? `Review: ${lastCompleted.title}`
          : 'Today’s Review'
      : activity === 'practice'
        ? activePractice?.title ?? 'Practice lessons'
        : activity === 'completed'
          ? activeCompleted?.title ?? 'Completed lessons'
          : activity === 'guidebook'
            ? 'Course guidebook'
            : 'Curated resources'

  const sessionBody =
    activity === 'mistakes'
      ? topMistake
        ? `You missed ${String((topMistake.exercise as { question?: string }).question || 'a step')
            .slice(0, 120)
            .replace(/\s*:?\s*$/, '')} in ${topMistake.lesson_title}. ` +
          'Answer it correctly twice in a row and it leaves this list.'
        : 'Nothing is queued right now.'
      : activity === 'rewind'
      ? rewindCopy
      : activity === 'practice'
        ? activePractice
          ? `Work through ${activePractice.title} to reinforce the concept with extra exercises.`
          : 'Unlock a practice lesson on the Learn path first.'
        : activity === 'completed'
          ? activeCompleted
            ? `Reopen ${activeCompleted.title} and retry the exercises you already finished.`
            : 'Complete a lesson on the Learn path first.'
          : activity === 'guidebook'
            ? 'Open the syntax and concept reference for the active course whenever you need a quick reminder.'
            : 'Interactive visualizers, official references, and companion checks matched to this course.'

  const outputLines = [
    isLoadingLesson ? 'Loading lesson…' : 'Ready',
    ...(mistakes.length > 0
      ? [`${mistakes.length} missed step${mistakes.length === 1 ? '' : 's'} queued for review`]
      : []),
    `${completedCount} lesson${completedCount === 1 ? '' : 's'} completed`,
    showResources
      ? `${completedMaterialIds.length}/${materials.length} resources completed`
      : null,
  ].filter(Boolean) as string[]

  return (
    <div className="ew-root ph-root" aria-label="Practice workspace">
      <header className="ew-topbar">
        <button
          type="button"
          className="ew-close"
          onClick={onBack}
          aria-label="Back to Learn"
          disabled={!onBack}
        >
          ✕
        </button>
        <div
          className="ew-progress"
          role="progressbar"
          aria-label="Course progress"
          aria-valuenow={completedCount}
          aria-valuemin={0}
          aria-valuemax={Math.max(lessons.length, 1)}
        >
          <div className="ew-progress-fill" style={{ width: `${progressPct}%` }} />
        </div>
        <div className="ew-topbar-actions">
          <span className="ew-topbar-link ph-topbar-stat">💪 Practice</span>
        </div>
      </header>

      <div className="ew-body">
        <aside className="ew-task-col" aria-label="Practice tasks">
          <span className="ew-section-label">Practice</span>
          <div className="ew-task-card">
            <div className="ew-task-badge">
              <span className="ew-task-badge-icon" aria-hidden="true">📋</span> YOUR TASK
            </div>
            <h2 className="ew-task-title">Today&apos;s Review</h2>
            <p className="ew-task-desc">
              Rewind a lesson, open extra practice, or check the guidebook — same tools as before, in one workspace.
            </p>
            <ol className="ew-task-steps">
              {steps.map((step, idx) => (
                <li key={step.id}>
                  <button
                    type="button"
                    className={`ph-step-btn ${activity === step.id ? 'is-selected' : ''} ${step.enabled ? '' : 'is-disabled'}`}
                    disabled={!step.enabled && step.id !== 'rewind' && step.id !== 'practice' && step.id !== 'completed'}
                    title={!step.enabled ? step.disabledReason : undefined}
                    onClick={() => setActivity(step.id)}
                  >
                    <span className="ew-step-num">{idx + 1}</span>
                    <span className="ph-step-copy">
                      <span className="ph-step-title">{step.title}</span>
                      <span className="ph-step-detail">{step.detail}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          </div>
        </aside>

        <div className="ew-workspace-pane">
          <div className="ew-workspace-columns">
            <main className="ew-editor-col" aria-label="Practice session">
              <div className="code-editor code-editor--workspace ph-session">
                <div className="code-editor-header">
                  <span className="code-editor-filename">
                    <span className="code-editor-file-icon" aria-hidden="true">
                      {fileIcon(filename)}
                    </span>
                    {filename}
                  </span>
                </div>
                <div className="ph-session-body">
                  <h3 className="ph-session-title">{sessionTitle}</h3>
                  <p className="ph-session-copy">{sessionBody}</p>

                  {activity === 'practice' && practiceLessons.length > 0 && (
                    <ul className="ph-session-list">
                      {practiceLessons.map((lesson) => (
                        <li key={lesson.id}>
                          <button
                            type="button"
                            className={`ph-lesson-chip ${activePractice?.id === lesson.id ? 'is-selected' : ''}`}
                            disabled={isLoadingLesson}
                            onClick={() => {
                              setSelectedPractice(lesson)
                              setActivity('practice')
                            }}
                          >
                            {lesson.title}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}

                  {activity === 'completed' && completed.length > 0 && (
                    <ul className="ph-session-list">
                      {completed.map((lesson) => (
                        <li key={lesson.id}>
                          <button
                            type="button"
                            className={`ph-lesson-chip ${activeCompleted?.id === lesson.id ? 'is-selected' : ''}`}
                            disabled={isLoadingLesson}
                            onClick={() => {
                              setSelectedCompleted(lesson)
                              setActivity('completed')
                            }}
                          >
                            {lesson.title}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}

                  {activity === 'resources' && showResources && onCompleteMaterial && (
                    <MaterialsView
                      variant="workspace"
                      materials={materials}
                      completedMaterialIds={completedMaterialIds}
                      onCompleteMaterial={onCompleteMaterial}
                    />
                  )}
                </div>
              </div>
            </main>

            <aside className="ew-output-col" aria-label="Output">
              <div className="ew-output-header">
                <span className="ew-output-label">Output</span>
              </div>
              <div className="ew-output-body" aria-live="polite">
                {outputLines.map((line) => (
                  <pre key={line} className="ew-output-line">
                    {line}
                  </pre>
                ))}
              </div>
            </aside>
          </div>

          <footer className="ew-footer">
            <div className="ew-footer-left">
              <button type="button" className="ew-btn ew-btn-back" onClick={onBack} disabled={!onBack}>
                <span aria-hidden="true">←</span> BACK
              </button>
            </div>
            <div className="ew-footer-right">
              {primary && (
                <button
                  type="button"
                  className="ew-btn ew-btn-submit"
                  disabled={!primary.enabled}
                  onClick={primary.run}
                >
                  {primary.label}
                </button>
              )}
            </div>
          </footer>
        </div>
      </div>
    </div>
  )
}
