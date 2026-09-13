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
