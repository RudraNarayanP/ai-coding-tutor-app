export interface GamificationState {
  streakCount: number
  lastActiveDate: string | null
  dailyXp: number
  dailyGoal: number
  boostMultiplier: number
  boostExpiresAt: number | null
}

const STORAGE_KEY = 'patchwork_gamification_v1'

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
