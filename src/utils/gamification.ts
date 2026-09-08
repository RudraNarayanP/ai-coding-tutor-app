export interface GamificationState {
  streakCount: number
  lastActiveDate: string | null
  dailyXp: number
  dailyGoal: number
  boostMultiplier: number
  boostExpiresAt: number | null
}

const STORAGE_KEY = 'patchwork_gamification_v1'

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

export function getGamificationState(): GamificationState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      const today = new Date().toISOString().split('T')[0]

      // Reset daily XP if day changed
      if (parsed.lastActiveDate !== today) {
        // Check if streak broke (>1 day missed)
        const yesterday = new Date(Date.now() - 86400000).toISOString().split('T')[0]
        const isConsecutive = parsed.lastActiveDate === yesterday

        return {
          ...parsed,
          streakCount: isConsecutive ? parsed.streakCount : 0,
          dailyXp: 0,
        }
      }
      return parsed
    }
  } catch {
    // Fallback
  }

  return {
    streakCount: 1,
    lastActiveDate: new Date().toISOString().split('T')[0],
    dailyXp: 0,
    dailyGoal: 30,
    boostMultiplier: 1,
    boostExpiresAt: null,
  }
}

export function saveGamificationState(state: GamificationState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    // Silent catch
  }
}

export function recordActivity(earnedXp: number): {
  state: GamificationState
  effectiveXp: number
  streakIncremented: boolean
  goalJustCompleted: boolean
} {
  const current = getGamificationState()
  const today = new Date().toISOString().split('T')[0]

  // Check XP Boost
  let multiplier = 1
  if (current.boostExpiresAt && Date.now() < current.boostExpiresAt) {
    multiplier = current.boostMultiplier || 2
  } else {
    current.boostExpiresAt = null
    current.boostMultiplier = 1
  }

  const effectiveXp = Math.round(earnedXp * multiplier)

  // Streak calculation
  let streakIncremented = false
  if (current.lastActiveDate !== today) {
    current.streakCount = (current.streakCount || 0) + 1
    current.lastActiveDate = today
    streakIncremented = true
  }

  const prevDailyXp = current.dailyXp || 0
  const nextDailyXp = prevDailyXp + effectiveXp
  const goalJustCompleted = prevDailyXp < current.dailyGoal && nextDailyXp >= current.dailyGoal

  current.dailyXp = nextDailyXp

  saveGamificationState(current)

  return {
    state: current,
    effectiveXp,
    streakIncremented,
    goalJustCompleted,
  }
}

export function activateXpBoost(durationMinutes: number = 15): GamificationState {
  const current = getGamificationState()
  current.boostMultiplier = 2
  current.boostExpiresAt = Date.now() + durationMinutes * 60 * 1000
  saveGamificationState(current)
  return current
}

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

export function getHearts(): number {
  try {
    const raw = localStorage.getItem('patchwork_hearts_count')
    return raw !== null ? parseInt(raw, 10) : 5
  } catch {
    return 5
  }
}

export function saveHearts(count: number): void {
  try {
    localStorage.setItem('patchwork_hearts_count', String(Math.max(0, count)))
  } catch {
    // ignore
  }
}

export function getUnlimitedHearts(): boolean {
  try {
    return localStorage.getItem('patchwork_unlimited_hearts') === 'true'
  } catch {
    return false
  }
}

export function setUnlimitedHearts(enabled: boolean): void {
  try {
    localStorage.setItem('patchwork_unlimited_hearts', String(enabled))
  } catch {
    // ignore
  }
}

export function getGems(): number {
  try {
    const raw = localStorage.getItem('patchwork_gems_count')
    return raw !== null ? parseInt(raw, 10) : 0
  } catch {
    return 0
  }
}

export function saveGems(count: number): void {
  try {
    localStorage.setItem('patchwork_gems_count', String(Math.max(0, count)))
  } catch {
    // ignore
  }
}
