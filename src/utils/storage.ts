export function safeSetItem(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch (err: any) {
    if (err && (err.name === 'QuotaExceededError' || err.code === 22 || err.code === 1014)) {
      console.warn(`localStorage quota exceeded when setting "${key}". Cleaning up draft storage...`)
      try {
        // Clear code drafts if storage is full to free space
        Object.keys(localStorage)
          .filter((k) => k.startsWith('patchwork_code_'))
          .forEach((k) => localStorage.removeItem(k))
        localStorage.setItem(key, value)
      } catch (retryErr) {
        console.error(`Failed to set "${key}" in localStorage after draft cleanup:`, retryErr)
      }
    } else {
      console.warn(`localStorage.setItem failed for key "${key}":`, err)
    }
  }
}

export function safeGetItem(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch (err) {
    console.warn(`localStorage.getItem failed for key "${key}":`, err)
    return null
  }
}

export function safeRemoveItem(key: string): void {
  try {
    localStorage.removeItem(key)
  } catch (err) {
    console.warn(`localStorage.removeItem failed for key "${key}":`, err)
  }
}

/**
 * Code drafts are stored as an envelope that records which starter code they
 * were based on. When the curriculum ships a new starter for a lesson — for
 * example when a leaked answer is replaced with a real skeleton — the stored
 * base no longer matches, so the draft is dropped and the learner sees the
 * fixed skeleton instead of stale text. Drafts written before envelopes
 * existed cannot be attributed to any starter and are dropped for the same
 * reason.
 */
const DRAFT_ENVELOPE_VERSION = 1

interface CodeDraftEnvelope {
  v: number
  base: string
  code: string
}

export function codeDraftKey(lessonId: string): string {
  return `patchwork_code_${lessonId}`
}

export function writeCodeDraft(key: string, starterCode: string, code: string): void {
  const envelope: CodeDraftEnvelope = {
    v: DRAFT_ENVELOPE_VERSION,
    base: starterCode,
    code,
  }
  safeSetItem(key, JSON.stringify(envelope))
}

export function readCodeDraft(key: string, starterCode: string): string | null {
  const raw = safeGetItem(key)
  if (raw === null) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    safeRemoveItem(key)
    return null
  }
  if (!isCodeDraftEnvelope(parsed) || parsed.v !== DRAFT_ENVELOPE_VERSION) {
    safeRemoveItem(key)
    return null
  }
  if (parsed.base !== starterCode) {
    safeRemoveItem(key)
    return null
  }
  return parsed.code
}

function isCodeDraftEnvelope(value: unknown): value is CodeDraftEnvelope {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Partial<CodeDraftEnvelope>
  return typeof candidate.base === 'string' && typeof candidate.code === 'string'
}
