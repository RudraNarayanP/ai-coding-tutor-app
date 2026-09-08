export interface GamificationState {
  streakCount: number
  lastActiveDate: string | null
  dailyXp: number
  dailyGoal: number
  boostMultiplier: number
  boostExpiresAt: number | null
  // Hearts system (Duolingo-style)
  hearts: number
  maxHearts: number
  unlimitedHearts: boolean
  // Strict daily progression
  currentDay: number
  totalDays: number
  dailyProgress: Record<string, boolean>
  // Progressive XP / level
  xp: number
  level: number
}

const STORAGE_KEY = 'patchwork_gamification_v1'
const GAME_STATE_KEY = 'patchwork_game_state_v1'

// ─── Level math ──────────────────────────────────────────────────────────────
// Levels grow quadratically so early levels feel fast and later levels feel
// like real milestones. xpForLevel(N) is the cumulative XP needed to reach N.

export function xpForLevel(level: number): number {
  if (level <= 1) return 0
  // Each level needs 60 + 40*(N-1) XP.
  let total = 0
  for (let i = 1; i < level; i++) total += 60 + 40 * (i - 1)
  return total
}

export function levelFromXp(xp: number): number {
  let level = 1
  while (xp >= xpForLevel(level + 1)) level += 1
  return level
}

export function xpIntoLevel(xp: number): { level: number; current: number; needed: number } {
  const level = levelFromXp(xp)
  const base = xpForLevel(level)
  const next = xpForLevel(level + 1)
  return { level, current: Math.max(0, xp - base), needed: Math.max(1, next - base) }
}

// ─── Date helpers ───────────────────────────────────────────────────────────

function getCurrentDate(): string {
  return new Date().toISOString().split('T')[0]
}

function getYesterdayDate(): string {
  return new Date(Date.now() - 86400000).toISOString().split('T')[0]
}

// ─── Full game-state save / restore ─────────────────────────────────────────

export interface GameSaveData {
  xp: number
  level: number
  hearts: number
  maxHearts: number
  unlimitedHearts: boolean
  currentDay: number
  totalDays: number
  dailyProgress: Record<string, boolean>
  streakCount: number
  dailyXp: number
  dailyGoal: number
  currentLessonId: string | null
}

export function loadFullGameState(): Partial<GamificationState> | null {
  try {
    const raw = localStorage.getItem(GAME_STATE_KEY)
    if (raw) return JSON.parse(raw) as Partial<GamificationState>
  } catch {
    // Fallback
  }
  return null
}

export function saveFullGameState(state: Partial<GamificationState>): void {
  try {
    localStorage.setItem(GAME_STATE_KEY, JSON.stringify(state))
  } catch {
    // Silent catch
  }
}

export function saveGameState(data: Partial<GameSaveData>): void {
  try {
    const existing = loadFullGameState() || {}
    const merged = { ...existing, ...data }
    localStorage.setItem(GAME_STATE_KEY, JSON.stringify(merged))
  } catch {
    // Silent catch
  }
}

export function restoreGameState(): Partial<GameSaveData> | null {
  return loadFullGameState() as Partial<GameSaveData> | null
}

// ─── Gamification state ─────────────────────────────────────────────────────

function normalizeState(raw: Record<string, any>, today: string): GamificationState {
  return {
    streakCount: typeof raw.streakCount === 'number' ? raw.streakCount : 0,
    lastActiveDate: typeof raw.lastActiveDate === 'string' ? raw.lastActiveDate : null,
    dailyXp: typeof raw.dailyXp === 'number' ? raw.dailyXp : 0,
    dailyGoal: typeof raw.dailyGoal === 'number' ? raw.dailyGoal : 30,
    boostMultiplier: typeof raw.boostMultiplier === 'number' ? raw.boostMultiplier : 1,
    boostExpiresAt: typeof raw.boostExpiresAt === 'number' ? raw.boostExpiresAt : null,
    hearts: typeof raw.hearts === 'number' ? raw.hearts : 5,
    maxHearts: typeof raw.maxHearts === 'number' ? raw.maxHearts : 5,
    unlimitedHearts: typeof raw.unlimitedHearts === 'boolean' ? raw.unlimitedHearts : false,
    currentDay: typeof raw.currentDay === 'number' ? raw.currentDay : 1,
    totalDays: typeof raw.totalDays === 'number' ? raw.totalDays : 1,
    dailyProgress: raw.dailyProgress && typeof raw.dailyProgress === 'object'
      ? raw.dailyProgress as Record<string, boolean>
      : { [today]: false },
    xp: typeof raw.xp === 'number' ? raw.xp : 0,
    level: typeof raw.level === 'number' ? raw.level : 1,
  }
}

export function getGamificationState(): GamificationState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      const today = getCurrentDate()
      const state = normalizeState(parsed, today)

      // New day → reset daily XP, restore hearts, advance day counter.
      if (state.lastActiveDate !== today) {
        const isConsecutive = state.lastActiveDate === getYesterdayDate()
        return {
          ...state,
          streakCount: isConsecutive ? state.streakCount : 0,
          lastActiveDate: today,
          dailyXp: 0,
          currentDay: state.currentDay + 1,
          dailyProgress: { ...state.dailyProgress, [today]: false },
          hearts: state.unlimitedHearts ? state.maxHearts : state.maxHearts,
          level: state.xp > 0 ? levelFromXp(state.xp) : state.level,
        }
      }
      return state
    }
  } catch {
    // Fallback
  }

  const today = getCurrentDate()
  return {
    streakCount: 0,
    lastActiveDate: today,
    dailyXp: 0,
    dailyGoal: 30,
    boostMultiplier: 1,
    boostExpiresAt: null,
    hearts: 5,
    maxHearts: 5,
    unlimitedHearts: false,
    currentDay: 1,
    totalDays: 1,
    dailyProgress: { [today]: false },
    xp: 0,
    level: 1,
  }
}

export function saveGamificationState(state: GamificationState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    // Silent catch
  }
}

// ─── Hearts system ──────────────────────────────────────────────────────────

export function getHearts(): number {
  const state = getGamificationState()
  if (state.unlimitedHearts) return state.maxHearts
  return state.hearts
}

export function loseHeart(): GamificationState {
  const current = getGamificationState()
  if (!current.unlimitedHearts && current.hearts > 0) {
    current.hearts = Math.max(0, current.hearts - 1)
  }
  saveGamificationState(current)
  saveFullGameState({ hearts: current.hearts, unlimitedHearts: current.unlimitedHearts })
  return current
}

export function restoreHearts(count: number = 1): GamificationState {
  const current = getGamificationState()
  current.hearts = Math.min(current.maxHearts, current.hearts + count)
  saveGamificationState(current)
  saveFullGameState({ hearts: current.hearts })
  return current
}

export function setUnlimitedHearts(value: boolean): GamificationState {
  const current = getGamificationState()
  current.unlimitedHearts = value
  if (value) current.hearts = current.maxHearts
  saveGamificationState(current)
  saveFullGameState({ unlimitedHearts: value, hearts: current.hearts })
  return current
}

export function setMaxHearts(value: number): GamificationState {
  const current = getGamificationState()
  current.maxHearts = Math.max(1, Math.min(10, value))
  current.hearts = current.unlimitedHearts ? current.maxHearts : Math.min(current.hearts, current.maxHearts)
  saveGamificationState(current)
  saveFullGameState({ maxHearts: current.maxHearts, hearts: current.hearts })
  return current
}

// ─── Strict daily progression ───────────────────────────────────────────────

export function markDailyProgress(completed: boolean = true): GamificationState {
  const current = getGamificationState()
  const today = getCurrentDate()
  current.dailyProgress[today] = completed
  current.totalDays = Math.max(current.totalDays, current.currentDay)
  saveGamificationState(current)
  saveFullGameState({ dailyProgress: current.dailyProgress, totalDays: current.totalDays })
  return current
}

export function getDailyProgress(): { currentDay: number; totalDays: number; streakDays: string[] } {
  const current = getGamificationState()
  const days = Object.keys(current.dailyProgress || {}).sort()
  return {
    currentDay: current.currentDay || 1,
    totalDays: current.totalDays || days.length,
    streakDays: days,
  }
}

// ─── Activity recording ─────────────────────────────────────────────────────

export function recordActivity(earnedXp: number): {
  state: GamificationState
  effectiveXp: number
  streakIncremented: boolean
  goalJustCompleted: boolean
} {
  const current = getGamificationState()
  const today = getCurrentDate()

  // XP boost multiplier
  let multiplier = 1
  if (current.boostExpiresAt && Date.now() < current.boostExpiresAt) {
    multiplier = current.boostMultiplier || 2
  } else {
    current.boostExpiresAt = null
    current.boostMultiplier = 1
  }

  const effectiveXp = Math.round(earnedXp * multiplier)

  // Daily streak
  let streakIncremented = false
  if (current.lastActiveDate !== today) {
    current.streakCount = (current.streakCount || 0) + 1
    current.lastActiveDate = today
    streakIncremented = true
  }

  // Daily XP goal + progressive total XP/level
  const prevDailyXp = current.dailyXp || 0
  const nextDailyXp = prevDailyXp + effectiveXp
  const goalJustCompleted = prevDailyXp < (current.dailyGoal || 30) && nextDailyXp >= (current.dailyGoal || 30)

  current.dailyXp = nextDailyXp
  current.xp = (current.xp || 0) + effectiveXp
  current.level = levelFromXp(current.xp)
  current.dailyProgress[today] = true
  current.totalDays = Math.max(current.totalDays, current.currentDay)

  saveGamificationState(current)
  saveFullGameState({ xp: current.xp, level: current.level, streakCount: current.streakCount })

  return { state: current, effectiveXp, streakIncremented, goalJustCompleted }
}

export function activateXpBoost(durationMinutes: number = 15): GamificationState {
  const current = getGamificationState()
  current.boostMultiplier = 2
  current.boostExpiresAt = Date.now() + durationMinutes * 60 * 1000
  saveGamificationState(current)
  saveFullGameState({ boostMultiplier: 2, boostExpiresAt: current.boostExpiresAt })
  return current
}

// ─── Sound ──────────────────────────────────────────────────────────────────

export function toggleSound(current: boolean): boolean {
  try {
    const next = !current
    localStorage.setItem('patchwork_sound_enabled', String(next))
    return next
  } catch {
    return current
  }
}

export function getSoundEnabled(): boolean {
  try {
    return localStorage.getItem('patchwork_sound_enabled') !== 'false'
  } catch {
    return true
  }
}