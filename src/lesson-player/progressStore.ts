import { useEffect, useState } from 'react'
import { getGamificationState, levelFromXp, saveGamificationState } from '../utils/gamification'

export type PlayerProgress = {
  xp: number
  hearts: number
  maxHearts: number
  streak: number
  lastActiveDate: string | null
  dailyXp: number
  dailyGoal: number
  gems: number
  streakFreezes: number
  completed: string[]
  seeded: boolean
}

const KEY = 'patchwork_lesson_player_v1'
const listeners = new Set<() => void>()

function today(): string {
  return new Date().toISOString().split('T')[0]
}

function yesterday(): string {
  return new Date(Date.now() - 86400000).toISOString().split('T')[0]
}

function empty(): PlayerProgress {
  const g = getGamificationState()
  return {
    xp: g.xp || 0,
    hearts: typeof g.hearts === 'number' ? g.hearts : 5,
    maxHearts: 5,
    streak: g.streakCount || 0,
    lastActiveDate: g.lastActiveDate,
    dailyXp: g.dailyXp || 0,
    dailyGoal: g.dailyGoal || 50,
    gems: 0,
    streakFreezes: 0,
    completed: [],
    seeded: false,
  }
}

function mirror(state: PlayerProgress) {
  const g = getGamificationState()
  g.xp = state.xp
  g.hearts = state.hearts
  g.maxHearts = state.maxHearts
  g.streakCount = state.streak
  g.lastActiveDate = state.lastActiveDate
  g.dailyXp = state.dailyXp
  g.dailyGoal = state.dailyGoal
  g.level = levelFromXp(state.xp)
  saveGamificationState(g)
}

function write(state: PlayerProgress) {
  localStorage.setItem(KEY, JSON.stringify(state))
  mirror(state)
  listeners.forEach((fn) => fn())
}

export function loadProgress(): PlayerProgress {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return empty()
    const parsed = JSON.parse(raw) as Partial<PlayerProgress>
    const base = empty()
    return {
      ...base,
      ...parsed,
      hearts: typeof parsed.hearts === 'number' ? parsed.hearts : base.hearts,
      maxHearts: 5,
      completed: Array.isArray(parsed.completed) ? parsed.completed : [],
      dailyGoal: typeof parsed.dailyGoal === 'number' ? parsed.dailyGoal : 50,
    }
  } catch {
    return empty()
  }
}

export function subscribeProgress(fn: () => void): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

export function updateProgress(mutator: (state: PlayerProgress) => void): PlayerProgress {
  const next = loadProgress()
  mutator(next)
  next.hearts = Math.max(0, Math.min(next.maxHearts, next.hearts))
  write(next)
  return next
}

/** Copy server profile numbers once, then the local store stays the source of truth. */
export function seedProgress(xp: number, streak: number) {
  updateProgress((state) => {
    if (state.seeded) return
    state.seeded = true
    if (xp > state.xp) state.xp = xp
    if (streak > state.streak) state.streak = streak
  })
}

function touchDay(state: PlayerProgress) {
  const day = today()
  if (state.lastActiveDate === day) {
    if (state.streak < 1) state.streak = 1
    return
  }
  if (state.lastActiveDate === yesterday()) {
    state.streak += 1
  } else if (state.lastActiveDate && state.streakFreezes > 0) {
    state.streakFreezes -= 1
    state.streak += 1
  } else {
    state.streak = 1
  }
  state.lastActiveDate = day
  state.dailyXp = 0
  state.hearts = state.maxHearts
}

export function awardXp(amount: number): PlayerProgress {
  return updateProgress((state) => {
    const day = today()
    if (state.lastActiveDate !== day) {
      const previousDaily = state.dailyXp
      touchDay(state)
      if (state.lastActiveDate === day && previousDaily !== 0) {
        /* touchDay already zeroed a new day */
      }
    }
    state.xp += amount
    state.dailyXp += amount
  })
}

export function loseHeart(): PlayerProgress {
  return updateProgress((state) => {
    state.hearts = Math.max(0, state.hearts - 1)
  })
}

export function earnHeart(): PlayerProgress {
  return updateProgress((state) => {
    state.hearts = Math.min(state.maxHearts, state.hearts + 1)
  })
}

export function markLessonComplete(id: string, gems: number): PlayerProgress {
  return updateProgress((state) => {
    if (!state.completed.includes(id)) state.completed.push(id)
    state.gems += gems
    const day = today()
    if (state.lastActiveDate !== day) touchDay(state)
  })
}

export function usePlayerProgress(): PlayerProgress {
  const [state, setState] = useState<PlayerProgress>(() => loadProgress())
  useEffect(() => subscribeProgress(() => setState(loadProgress())), [])
  return state
}

export function buyStreakFreeze(): { ok: boolean; state: PlayerProgress } {
  const current = loadProgress()
  if (current.gems < 10) return { ok: false, state: current }
  const state = updateProgress((next) => {
    next.gems -= 10
    next.streakFreezes += 1
  })
  return { ok: true, state }
}
