import { PatchworkCharacter } from '../PatchworkCharacters'
import '../../lesson-player/lessonPlayer.css'

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

function friendlyTitle(title: string): string {
  return title.replace(/^\d+\.\s*/, '').replace(/`([^`]+)`/g, '$1')
}

function isBoss(lesson: PathLesson): boolean {
  return lesson.type === 'checkpoint' || lesson.type === 'challenge' || /gobble/i.test(lesson.title)
}

function nodeIcon(lesson: PathLesson): string {
  if (lesson.status === 'completed') return '👑'
  if (isBoss(lesson)) return '🎁'
  if (lesson.status === 'locked') return '🔒'
  return '★'
}

const UNIT_COLORS = ['#1cb0f6', '#ce82ff', '#ff9600', '#58cc02', '#ff4b4b']

function unitColor(unitId: string, index: number): string {
  if (unitId === 'booleans') return '#1cb0f6'
  return UNIT_COLORS[index % UNIT_COLORS.length]
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
        <button type="button" className="duo-guidebook-btn" onClick={onOpenGuidebook} aria-label="Guidebook">
          Guide
        </button>
      ) : null}
      <nav aria-label="Lessons" className="duo-path-tree">
        {unitGroups.map((unit, unitIndex) => {
          const color = unitColor(unit.id, unitIndex)
          const bannerTitle = unit.id === 'booleans' ? 'Booleans' : unit.title
          const bannerIndex = unit.id === 'booleans' ? 1 : unitIndex + 1
          return (
            <section key={unit.id}>
              <div className="duo-unit-banner" style={{ background: color }}>
                <div className="duo-unit-info">
                  <span className="duo-unit-subtitle">UNIT {bannerIndex}</span>
                  <span className="duo-unit-title">{bannerTitle}</span>
                </div>
              </div>
              {unit.lessons.map((item) => {
                const idx = lessons.findIndex((lesson) => lesson.id === item.id)
                const isActive = activeLessonId === item.id
                const offset = OFFSETS[(idx < 0 ? 0 : idx) % OFFSETS.length]
                const showMascot = currentLesson?.id === item.id
                const boss = isBoss(item)
                return (
                  <div
                    key={item.id}
                    className="duo-path-row duo-path-serpentine"
                    style={{ transform: `translateX(${offset}px)` }}
                  >
                    <div>
                      <button
                        id={`lesson-node-${item.id}`}
                        className={`duo-path-circle-btn ${item.status}${boss && item.status !== 'completed' ? ' duo-path-circle-btn--boss' : ''}${item.status === 'current' ? ' duo-path-circle-btn--pulse' : ''}`}
                        style={item.status === 'current' ? { background: color, boxShadow: '0 6px 0 rgba(0,0,0,0.35)' } : undefined}
                        onClick={() => onSelectLesson(item)}
                        disabled={item.status === 'locked' || isLoadingLesson}
                        title={friendlyTitle(item.title)}
                        aria-current={isActive ? 'page' : undefined}
                        aria-label={`${friendlyTitle(item.title)} — ${statusLabel(item, isActive)}${boss ? ' — boss checkpoint' : ''}${item.xp_reward ? `, ${item.xp_reward} XP reward` : ''}`}
                      >
                        {item.status === 'current' && <div className="duo-start-dialog">START</div>}
                        <span>{nodeIcon(item)}</span>
                      </button>
                      <span className="duo-path-label">{friendlyTitle(item.title)}</span>
                    </div>
                    {showMascot ? (
                      <div className="duo-path-mascot">
                        <PatchworkCharacter name="patch" state="idle" size={72} />
                      </div>
                    ) : null}
                  </div>
                )
              })}
            </section>
          )
        })}
      </nav>
    </div>
  )
}
