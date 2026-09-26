import { safeGetItem, safeSetItem } from './storage'

const ID_KEY = 'patchwork_learner_id'
const NAME_KEY = 'patchwork_display_name'

export type LearnerIdentity = {
  userId: string
  displayName: string
}

function mintUserId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `learner_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`
}

function defaultDisplayName(userId: string): string {
  const short = userId.replace(/-/g, '').slice(0, 6)
  return `Learner_${short}`
}

/** Stable per-browser identity so live leaderboard ranks stay per real person. */
export function getLearnerIdentity(): LearnerIdentity {
  let userId = safeGetItem(ID_KEY)
  if (!userId) {
    userId = mintUserId()
    safeSetItem(ID_KEY, userId)
  }
  let displayName = safeGetItem(NAME_KEY)
  if (!displayName) {
    displayName = defaultDisplayName(userId)
    safeSetItem(NAME_KEY, displayName)
  }
  return { userId, displayName }
}

export function setDisplayName(name: string): LearnerIdentity {
  const trimmed = name.trim().slice(0, 32)
  const { userId } = getLearnerIdentity()
  const displayName = trimmed || defaultDisplayName(userId)
  safeSetItem(NAME_KEY, displayName)
  return { userId, displayName }
}