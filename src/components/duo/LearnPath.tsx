import { PatchworkCharacter } from '../PatchworkCharacters'

export type PathLesson = {
  id: string
  title: string
  order: number
  difficulty: string
  duration_minutes: number
  status: 'completed' | 'current' | 'locked'
  type?: 'learn' | 'practice' | 'checkpoint' | 'challenge'
  xp_reward?: number
  unit_id?: string
  unit_title?: string
  section_id?: string
  section_title?: string
}

interface LearnPathProps {
  lessons: PathLesson[]
  activeLessonId: string | null
  isLoadingLesson: boolean
  onSelectLesson: (lesson: PathLesson) => void
  onOpenGuidebook: () => void
}

function statusLabel(lesson: PathLesson, isActive: boolean): string {
  if (lesson.status === 'completed') return 'Completed'
  if (lesson.status === 'locked') return 'Locked'
  if (lesson.status === 'current' || isActive) return 'Current lesson'
  return 'Available'
}

function nodeIcon(lesson: PathLesson): string {
  if (lesson.status === 'completed') return '✓'
  if (lesson.type === 'checkpoint') return '👑'
  if (lesson.type === 'challenge') return '⚡'
  if (lesson.type === 'practice') return '📖'
  return '⭐'
}

const OFFSETS = [0, 52, 88, 52, 0, -52, -88, -52]

export function LearnPath({
  lessons,
  activeLessonId,
  isLoadingLesson,
  onSelectLesson,
  onOpenGuidebook,
}: LearnPathProps) {
  const currentLesson = lessons.find((l) => l.status === 'current') || lessons.find((l) => l.id === activeLessonId)

  const unitsMap = new Map<string, { id: string; title: string; sectionTitle?: string; lessons: PathLesson[] }>()
  lessons.forEach((item, idx) => {
    const unitId = item.unit_id || `unit-${Math.floor(idx / 4) + 1}`
    const unitTitle = item.unit_title || `Unit ${Math.floor(idx / 4) + 1}`
    if (!unitsMap.has(unitId)) {
      unitsMap.set(unitId, { id: unitId, title: unitTitle, sectionTitle: item.section_title, lessons: [] })
    }
    unitsMap.get(unitId)!.lessons.push(item)
  })
  const unitGroups = Array.from(unitsMap.values())
  const focusIndex = Math.max(
    0,
    unitGroups.findIndex((u) => u.lessons.some((l) => l.id === currentLesson?.id))
  )
  const focusUnit = unitGroups[focusIndex] ?? unitGroups[0]

  return (
    <div className="duo-learn-stage">
      {focusUnit ? (
        <div className="duo-unit-banner duo-unit-banner-cyan">
          <div className="duo-unit-info">
            <span className="duo-unit-subtitle">
              {focusUnit.sectionTitle ? `${focusUnit.sectionTitle} · ` : ''}UNIT {focusIndex + 1}
            </span>
            <span className="duo-unit-title">{focusUnit.title}</span>
          </div>
          <button type="button" className="duo-guidebook-btn" onClick={onOpenGuidebook}>
            GUIDEBOOK
          </button>
        </div>
      ) : null}

      <nav aria-label="Lessons" className="duo-path-tree">
        {lessons.map((item, idx) => {
          const isActive = activeLessonId === item.id
          const offset = OFFSETS[idx % OFFSETS.length]
          const showMascot = currentLesson?.id === item.id
          return (
            <div
              key={item.id}
              className="duo-path-row duo-path-serpentine"
              style={{ transform: `translateX(${offset}px)` }}
            >
              <button
                id={`lesson-node-${item.id}`}
                className={`duo-path-circle-btn ${item.status}${item.type === 'checkpoint' ? ' duo-path-circle-btn--boss' : ''}${item.status === 'current' ? ' duo-path-circle-btn--pulse' : ''}`}
                onClick={() => onSelectLesson(item)}
                disabled={item.status === 'locked' || isLoadingLesson}
                title={item.title}
                aria-current={isActive ? 'page' : undefined}
                aria-label={`${item.title} — ${statusLabel(item, isActive)}${item.type === 'checkpoint' ? ' — boss checkpoint' : ''}${item.xp_reward ? `, ${item.xp_reward} XP reward` : ''}`}
              >
                {item.status === 'current' && <div className="duo-start-dialog">START</div>}
                <span>{nodeIcon(item)}</span>
              </button>
              {item.status !== 'locked' && item.xp_reward ? (
                <span
                  className={`duo-path-xp-badge${item.type === 'checkpoint' ? ' duo-path-xp-badge--boss' : ''}`}
                >
                  {item.type === 'checkpoint' ? '👑 ' : ''}+{item.xp_reward} XP
                </span>
              ) : null}
              {showMascot ? (
                <div className="duo-path-mascot">
                  <PatchworkCharacter name="patch" state="idle" size={72} />
                </div>
              ) : null}
            </div>
          )
        })}
      </nav>
    </div>
  )
}
