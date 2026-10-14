/** Tabs that map to URL hash segments for in-app browser back/forward. */
export type AppTab =
  | 'learn'
  | 'practice'
  | 'quests'
  | 'courses'
  | 'create'
  | 'leaderboards'
  | 'profile'

export type AppLocation = {
  tab: AppTab
  /** When set, the learn tab is showing this lesson workspace. */
  lessonId?: string | null
}

const VALID_TABS = new Set<AppTab>([
  'learn',
  'practice',
  'quests',
  'courses',
  'create',
  'leaderboards',
  'profile',
])

export function isAppTab(value: string): value is AppTab {
  return VALID_TABS.has(value as AppTab)
}

/** Default landing location when the hash is missing or invalid. */
export const DEFAULT_APP_LOCATION: AppLocation = { tab: 'learn', lessonId: null }

export function locationToHash(loc: AppLocation): string {
  const tab = isAppTab(loc.tab) ? loc.tab : 'learn'
  const lessonId = loc.lessonId?.trim()
  if (lessonId && tab === 'learn') {
    return `#/learn/${encodeURIComponent(lessonId)}`
  }
  return `#/${tab}`
}

export function hashToLocation(hash: string): AppLocation {
  const raw = hash.replace(/^#/, '').replace(/^\//, '').trim()
  if (!raw) return { ...DEFAULT_APP_LOCATION }

  const parts = raw.split('/').filter(Boolean)
  if (parts[0] === 'learn') {
    if (parts[1]) {
      try {
        return { tab: 'learn', lessonId: decodeURIComponent(parts[1]) }
      } catch {
        return { tab: 'learn', lessonId: parts[1] }
      }
    }
    return { tab: 'learn', lessonId: null }
  }

  if (isAppTab(parts[0])) {
    return { tab: parts[0], lessonId: null }
  }

  return { ...DEFAULT_APP_LOCATION }
}

export function readAppLocationFromWindow(): AppLocation {
  return hashToLocation(window.location.hash)
}

let stackedNavigations = 0

/** In-app pushes since the last replace (used for back-button fallbacks). */
export function getAppHistoryStackDepth(): number {
  return stackedNavigations
}

export function resetAppHistoryStack(): void {
  stackedNavigations = 0
}

export function consumeAppHistoryPop(): void {
  stackedNavigations = Math.max(0, stackedNavigations - 1)
}

export function writeAppHistory(loc: AppLocation, mode: 'push' | 'replace' = 'push'): void {
  const hash = locationToHash(loc)
  const state = { patchwork: loc }
  if (mode === 'replace') {
    stackedNavigations = 0
    window.history.replaceState(state, '', hash)
  } else {
    stackedNavigations += 1
    window.history.pushState(state, '', hash)
  }
}
