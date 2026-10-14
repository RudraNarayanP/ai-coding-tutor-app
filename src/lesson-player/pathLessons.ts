import type { PathLesson } from '../components/duo/LearnPath'
import { booleanChain } from './lessons'
import { loadProgress } from './progressStore'

const TITLES: Record<string, string> = {
  booleans: 'True or False',
  'booleans-step-1': 'And',
  'booleans-step-2': 'Or',
  'booleans-step-3': 'Flip it with not',
  'booleans-combine': 'Combine',
  'booleans-01': 'Ghost Gobble',
}

const CHAIN_META: { id: string; title: string; type: PathLesson['type'] }[] = [
  { id: 'booleans', title: 'True or False', type: 'learn' },
  { id: 'booleans-step-1', title: 'And', type: 'learn' },
  { id: 'booleans-step-2', title: 'Or', type: 'learn' },
  { id: 'booleans-step-3', title: 'Flip it with not', type: 'learn' },
  { id: 'booleans-combine', title: 'Combine', type: 'learn' },
  { id: 'booleans-01', title: 'Ghost Gobble', type: 'challenge' },
]

function withLocalStatus(chain: PathLesson[]): PathLesson[] {
  const done = new Set(loadProgress().completed)
  let opened = false
  return chain.map((lesson) => {
    if (done.has(lesson.id)) return { ...lesson, status: 'completed' as const }
    if (!opened) {
      opened = true
      return { ...lesson, status: 'current' as const }
    }
    return { ...lesson, status: 'locked' as const }
  })
}

function offlineBooleanPath(): PathLesson[] {
  return withLocalStatus(
    CHAIN_META.map((item, index) => ({
      id: item.id,
      title: item.title,
      order: index + 1,
      difficulty: 'beginner',
      duration_minutes: 5,
      status: 'locked',
      type: item.type,
      unit_id: 'booleans',
      unit_title: 'Booleans',
      xp_reward: 10,
    }))
  )
}

export function decoratePathLessons(lessons: PathLesson[]): PathLesson[] {
  if (!lessons.some((lesson) => lesson.id === 'booleans-step-3')) {
    return lessons.length === 0 ? offlineBooleanPath() : lessons
  }

  const byId = new Map(lessons.map((lesson) => [lesson.id, lesson]))
  const ghost = byId.get('booleans-01')
  const chain: PathLesson[] = []
  for (const id of booleanChain) {
    const found = byId.get(id)
    if (found) {
      chain.push({
        ...found,
        title: TITLES[id] ?? found.title,
        unit_id: 'booleans',
        unit_title: 'Booleans',
      })
    } else if (id === 'booleans-combine' && ghost) {
      chain.push({
        ...ghost,
        id: 'booleans-combine',
        title: 'Combine',
        type: 'learn',
        unit_id: 'booleans',
        unit_title: 'Booleans',
        xp_reward: 10,
      })
    }
  }

  const rest = lessons.filter((lesson) => !booleanChain.includes(lesson.id as (typeof booleanChain)[number]))
  return [...withLocalStatus(chain), ...rest]
}
